"""Bounded, non-intrusive collectors for Discovery Intelligence.

Collectors return observations and evidence; they never write to the CMDB directly.
Credentialed collectors are opt-in and use the platform's existing credential stores.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import random
import socket
import ssl
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import or_, select

from app.models.active_directory import ActiveDirectoryObject
from app.models.discovery_intelligence import DiscoveryCredential, DiscoveryDHCPLease
from app.models.snmp import SNMPDeviceProfile, SNMPTarget
from app.services.discovery_intelligence_service import SERVICE_PORTS, normalize_hostname
from app.services.snmp_client_service import SNMPClientError, SecureSNMPClient
from app.services.secret_encryption_service import SecretEncryptionService


def evidence(kind: str, source: str, value, *, verified: bool = False):
    return {
        "evidence_type": kind, "source": source, "value": value,
        "normalized_value": str(value).strip().lower()[:500], "verified": verified,
    }


@dataclass
class CollectedObservation:
    ip_address: str
    hostnames: list[str] = field(default_factory=list)
    mac_address: str | None = None
    vendor: str | None = None
    operating_system: str | None = None
    open_ports: list[int] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "CollectedObservation"):
        self.hostnames = list(dict.fromkeys(self.hostnames + other.hostnames))
        self.mac_address = other.mac_address or self.mac_address
        self.vendor = other.vendor or self.vendor
        self.operating_system = other.operating_system or self.operating_system
        self.open_ports = sorted(set(self.open_ports + other.open_ports))
        self.data.update({key: value for key, value in other.data.items() if value not in (None, "", [], {})})
        self.evidence.extend(other.evidence)
        self.warnings.extend(other.warnings)
        return self

    def as_dict(self):
        return {
            "ip_address": self.ip_address,
            "hostname": self.hostnames[0] if self.hostnames else None,
            "hostnames": self.hostnames, "mac_address": self.mac_address,
            "vendor": self.vendor, "operating_system": self.operating_system,
            "open_ports": self.open_ports, "evidence": self.evidence, **self.data,
        }


class DNSCorrelationCollector:
    def __init__(self, reverse: Callable = socket.gethostbyaddr, forward: Callable = socket.getaddrinfo):
        self.reverse, self.forward = reverse, forward

    def collect(self, ip: str):
        result = CollectedObservation(ip)
        try:
            primary, aliases, _addresses = self.reverse(ip)
            candidates = [primary, *aliases]
            for name in candidates:
                normalized = normalize_hostname(name)
                if not normalized:
                    continue
                forward_addresses = {row[4][0] for row in self.forward(normalized, None)}
                if ip in forward_addresses:
                    result.hostnames.append(normalized)
                    result.evidence.append(evidence("hostname_match", "forward_confirmed_dns", normalized, verified=True))
                else:
                    result.warnings.append(f"PTR hostname {normalized} did not resolve back to {ip}.")
        except (OSError, socket.error):
            pass
        return result


class NetBIOSNameCollector:
    """One bounded RFC 1002 node-status request; no broadcast and no enumeration."""
    def __init__(self, socket_factory=lambda: socket.socket(socket.AF_INET,socket.SOCK_DGRAM), timeout=1.0):self.socket_factory=socket_factory;self.timeout=timeout
    @staticmethod
    def _query(transaction_id):
        raw=b"*"+b" "*15;encoded=b"".join(bytes((65+(value>>4),65+(value&15))) for value in raw)
        return struct.pack("!HHHHHH",transaction_id,0,1,0,0,0)+bytes((32,))+encoded+b"\x00"+struct.pack("!HH",0x21,1)
    def collect(self,ip):
        result=CollectedObservation(ip);transaction_id=random.SystemRandom().randrange(1,65535);sock=self.socket_factory()
        try:
            sock.settimeout(self.timeout);sock.sendto(self._query(transaction_id),(ip,137));payload,_=sock.recvfrom(4096)
            if len(payload)<63 or struct.unpack("!H",payload[:2])[0]!=transaction_id:return result
            offset=50
            if payload[offset:offset+2].startswith(b"\xc0"):offset+=2
            else:
                while offset<len(payload) and payload[offset]:offset+=payload[offset]+1
                offset+=1
            offset+=10
            if offset>=len(payload):return result
            count=payload[offset];offset+=1
            for _ in range(min(count,100)):
                entry=payload[offset:offset+18];offset+=18
                if len(entry)<18:break
                name=entry[:15].decode("ascii","ignore").strip();suffix=entry[15];flags=struct.unpack("!H",entry[16:18])[0]
                if suffix in (0x00,0x20) and not flags&0x8000:
                    normalized=normalize_hostname(name)
                    if normalized:result.hostnames.append(normalized);result.evidence.append(evidence("hostname_match","netbios_node_status",normalized,verified=True));break
        except OSError:pass
        finally:sock.close()
        return result


class ActiveDirectoryCorrelationCollector:
    """Correlate already-synchronized AD computer objects without contacting AD."""
    def __init__(self, db): self.db = db

    def collect(self, ip: str, hostnames: list[str]):
        result = CollectedObservation(ip)
        short_names = {name.split(".")[0].lower() for name in hostnames if name}
        if not short_names:
            return result
        rows = self.db.scalars(select(ActiveDirectoryObject).where(
            ActiveDirectoryObject.object_type == "computer",
            or_(
                *[ActiveDirectoryObject.dns_hostname.ilike(name) for name in hostnames],
                *[ActiveDirectoryObject.sam_account_name.ilike(name + "$") for name in short_names],
                *[ActiveDirectoryObject.common_name.ilike(name) for name in short_names],
            ),
        ).limit(5)).all()
        if len(rows) == 1:
            row = rows[0]
            canonical = normalize_hostname(row.dns_hostname or row.common_name or row.sam_account_name.rstrip("$"))
            if canonical:
                result.hostnames.append(canonical)
            result.operating_system = row.operating_system
            result.data["version"] = row.operating_system_version
            result.evidence.append(evidence("ad_match", "active_directory", row.object_guid, verified=True))
            if row.operating_system:
                result.evidence.append(evidence("operating_system", "active_directory", row.operating_system, verified=True))
        elif len(rows) > 1:
            result.warnings.append("Multiple Active Directory computer objects matched; no canonical AD identity was selected.")
        return result


class DHCPLeaseCorrelationCollector:
    """Correlate leases imported from an administrator-approved DHCP source."""
    def __init__(self, db): self.db = db
    def collect(self, ip: str):
        result=CollectedObservation(ip)
        row=self.db.scalar(select(DiscoveryDHCPLease).where(DiscoveryDHCPLease.ip_address==ip).order_by(DiscoveryDHCPLease.last_imported_at.desc()))
        if not row:return result
        name=normalize_hostname(row.hostname)
        if name:result.hostnames.append(name);result.evidence.append(evidence("hostname_match","dhcp_lease",name,verified=True))
        if row.mac_address:result.mac_address=row.mac_address;result.evidence.append(evidence("mac_address","dhcp_lease",row.mac_address,verified=True))
        result.data["dhcp_lease"]={"source":row.source,"lease_server":row.lease_server,"expires_at":row.expires_at}
        return result


class ServiceFingerprintCollector:
    """Small allowlisted TCP checks and bounded banners; not a vulnerability scanner."""
    def __init__(self, connector=socket.create_connection, timeout: float = 1.5, max_banner=1024):
        self.connector, self.timeout, self.max_banner = connector, timeout, max_banner

    def _tls(self, ip: str, port: int):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with self.connector((ip, port), timeout=self.timeout) as raw:
            with context.wrap_socket(raw, server_hostname=ip) as wrapped:
                cert = wrapped.getpeercert()
                return {
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "subject_alt_names": [x[1] for x in cert.get("subjectAltName", [])],
                    "not_before": cert.get("notBefore"), "not_after": cert.get("notAfter"),
                }

    def collect(self, ip: str, ports: list[int]):
        result = CollectedObservation(ip)
        banners, certificates, http_headers = {}, [], {}
        approved=[port for port in sorted(set(ports))[:32] if port in SERVICE_PORTS]
        def probe(port):
            try:
                with self.connector((ip, port), timeout=self.timeout) as connection:
                    connection.settimeout(self.timeout)
                    banner = b""
                    if port in {21, 22, 25, 110, 143, 6379}:
                        banner = connection.recv(self.max_banner)
                    return port,banner.decode("utf-8", "replace")[:self.max_banner]
            except OSError:
                return None
        with ThreadPoolExecutor(max_workers=min(16,max(1,len(approved)))) as pool:
            for future in as_completed([pool.submit(probe,port) for port in approved]):
                opened=future.result()
                if not opened:continue
                port,banner=opened;result.open_ports.append(port);banners[str(port)]=banner
        result.open_ports.sort()
        for port in result.open_ports:
            if port in {443, 636, 2376, 5986, 6443}:
                try:
                    certificates.append({"port": port, **self._tls(ip, port)})
                except (OSError, ssl.SSLError):
                    result.warnings.append(f"TLS certificate inspection failed safely on port {port}.")
            if port in {80,443}:
                connection_class=http.client.HTTPSConnection if port==443 else http.client.HTTPConnection
                try:
                    connection=connection_class(ip,port,timeout=self.timeout,context=ssl._create_unverified_context()) if port==443 else connection_class(ip,port,timeout=self.timeout)
                    connection.request("HEAD","/");response=connection.getresponse();http_headers[str(port)]={key.lower():value[:500] for key,value in response.getheaders()};connection.close()
                except (OSError,http.client.HTTPException,ssl.SSLError):pass
        if result.open_ports:
            result.evidence.append(evidence("service_fingerprint", "tcp_banner", result.open_ports, verified=True))
        if banners:
            result.data["service_banners"] = banners
            result.data["ssh_banner"] = banners.get("22")
        if certificates:
            result.data["certificates"] = certificates
        if http_headers:
            result.data["http_headers"]=http_headers
            result.data["http_server"]=next((headers.get("server") for headers in http_headers.values() if headers.get("server")),None)
        return result


class SNMPDiscoveryCollector:
    ENTITY_OIDS = {
        "manufacturer": "1.3.6.1.2.1.47.1.1.1.1.12.1",
        "model": "1.3.6.1.2.1.47.1.1.1.1.13.1",
        "serial_number": "1.3.6.1.2.1.47.1.1.1.1.11.1",
        "firmware": "1.3.6.1.2.1.47.1.1.1.1.10.1",
    }

    def __init__(self, db, client_factory=SecureSNMPClient):
        self.db, self.client_factory = db, client_factory

    def target_for(self, ip: str):
        return self.db.scalar(select(SNMPTarget).where(SNMPTarget.ip_address == ip, SNMPTarget.enabled.is_(True)))

    @staticmethod
    def _value(value):
        return value.value_text if value and value.value_text is not None else value.value_numeric if value else None

    def collect(self, ip: str, authorized_ranges: list[str]):
        result = CollectedObservation(ip)
        target = self.target_for(ip)
        if not target:
            result.warnings.append("No enabled SNMP target is configured for this address.")
            return result
        client = None
        try:
            client = self.client_factory(target, target.credential, authorized_networks=authorized_ranges)
            identity = client.get_system_identity()
            values = {key: self._value(value) for key, value in identity.items()}
            name = normalize_hostname(values.get("system.name"))
            if name: result.hostnames.append(name)
            description = values.get("system.description")
            result.data.update({"snmp_description": description, "uptime": values.get("system.uptime"), "snmp_object_id": values.get("system.object_id")})
            inventory = client.get_many(list(self.ENTITY_OIDS.values()))
            for key, value in zip(self.ENTITY_OIDS, inventory):
                parsed = self._value(value)
                if parsed: result.data[key] = parsed
            profile = self.db.get(SNMPDeviceProfile, target.detected_profile_id) if target.detected_profile_id else None
            if profile:
                result.vendor = profile.vendor
                result.data["snmp_device_type"] = profile.device_type
            elif result.data.get("manufacturer"):
                result.vendor = result.data["manufacturer"]
            result.evidence.append(evidence("snmp", f"snmp_{target.version}", values.get("system.object_id") or target.id, verified=True))
            if name: result.evidence.append(evidence("hostname_match", "snmp_sysName", name, verified=True))
            if result.vendor: result.evidence.append(evidence("vendor_match", "snmp_profile", result.vendor, verified=True))
            target.last_test_status = "success"
        except SNMPClientError as error:
            result.warnings.append(f"SNMP {error.category}: {error.safe_message}")
            target.last_test_status = error.category
            target.last_test_message = error.safe_message[:500]
        finally:
            if client:
                client.close()
        return result


class CommandFingerprintCollector:
    """Transport-neutral allowlisted WinRM/SSH parsing; executors are injected by adapters/tests."""
    LINUX_COMMANDS = ("hostname -f", "cat /etc/os-release", "uname -r", "uptime -s")
    WINDOWS_COMMANDS = (
        "Get-CimInstance Win32_ComputerSystem | Select Name,Domain,Manufacturer,Model,TotalPhysicalMemory",
        "Get-CimInstance Win32_OperatingSystem | Select Caption,Version,LastBootUpTime",
        "Get-CimInstance Win32_BIOS | Select SerialNumber,SMBIOSBIOSVersion",
    )

    def collect(self, ip: str, platform: str, executor: Callable[[str], str]):
        result = CollectedObservation(ip)
        commands = self.WINDOWS_COMMANDS if platform == "windows" else self.LINUX_COMMANDS
        outputs = {}
        for command in commands:
            outputs[command] = executor(command)[:20000]
        result.data[f"{platform}_inventory"] = outputs
        blob = "\n".join(outputs.values())
        if platform == "linux":
            match = next((line.split("=", 1)[1].strip('"') for line in blob.splitlines() if line.startswith("PRETTY_NAME=")), None)
            result.operating_system = match or "Linux"
        else:
            result.operating_system = "Windows"
        result.evidence.append(evidence("operating_system", f"{platform}_credentialed", result.operating_system, verified=True))
        return result


class CredentialedHostCollector:
    """Execute fixed read-only commands through optional SSH or WinRM transports."""
    def __init__(self, db): self.db = db

    def _credential(self, policy_id, ip: str, kinds: tuple[str, ...]):
        rows = self.db.scalars(select(DiscoveryCredential).where(
            DiscoveryCredential.policy_id == policy_id,
            DiscoveryCredential.enabled.is_(True),
            DiscoveryCredential.credential_type.in_(kinds),
        ).order_by(DiscoveryCredential.created_at)).all()
        address = ipaddress.ip_address(ip)
        for row in rows:
            if not row.scope_cidr or address in ipaddress.ip_network(row.scope_cidr, strict=False): return row
        return None

    @staticmethod
    def _ssh_executor(ip: str, username: str, secret: str, timeout: float):
        try: import paramiko
        except ImportError as error: raise RuntimeError("SSH transport dependency is not installed.") from error
        client = paramiko.SSHClient();client.set_missing_host_key_policy(paramiko.RejectPolicy());client.load_system_host_keys()
        client.connect(ip, username=username, password=secret, timeout=timeout, allow_agent=False, look_for_keys=False)
        def execute(command: str):
            _stdin, stdout, _stderr = client.exec_command(command, timeout=timeout)
            return stdout.read(20000).decode("utf-8", "replace")
        return client, execute

    @staticmethod
    def _winrm_executor(ip: str, username: str, secret: str, timeout: float, tls: bool):
        try: import winrm
        except ImportError as error: raise RuntimeError("WinRM transport dependency is not installed.") from error
        endpoint = f"{'https' if tls else 'http'}://{ip}:{5986 if tls else 5985}/wsman"
        session = winrm.Session(endpoint, auth=(username, secret), transport="ntlm", server_cert_validation="validate", read_timeout_sec=max(2, int(timeout)), operation_timeout_sec=max(1, int(timeout)-1))
        def execute(command: str):
            response = session.run_ps(command)
            if response.status_code != 0: raise RuntimeError("WinRM read-only inventory command failed.")
            return response.std_out.decode("utf-8", "replace")
        return None, execute

    def collect(self, policy_id, ip: str, open_ports: list[int], timeout: float):
        result = CollectedObservation(ip);platform=credential=None
        if 5986 in open_ports or 5985 in open_ports: platform,credential="windows",self._credential(policy_id,ip,("winrm","wmi"))
        elif 22 in open_ports: platform,credential="linux",self._credential(policy_id,ip,("ssh",))
        if not platform or not credential: return result
        secret=SecretEncryptionService.decrypt(credential.secret_ciphertext,environment_key="HIOP_DISCOVERY_CREDENTIAL_KEY");resource=None
        try:
            if platform=="windows": resource,executor=self._winrm_executor(ip,credential.username or "",secret,timeout,5986 in open_ports)
            else: resource,executor=self._ssh_executor(ip,credential.username or "",secret,timeout)
            result.merge(CommandFingerprintCollector().collect(ip,platform,executor));credential.last_used_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        except Exception as error: result.warnings.append(f"{platform.title()} credentialed fingerprinting failed safely: {str(error)[:180]}")
        finally:
            secret=""
            if resource: resource.close()
        return result
