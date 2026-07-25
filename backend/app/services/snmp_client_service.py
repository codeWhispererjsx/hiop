"""Secure bounded PySNMP client.

The transport adapter is injectable so tests never need a network agent.
"""
import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable

from app.core.config import settings
from app.services.snmp_secret_service import SNMPSecretError, SNMPSecretService

SYSTEM_OIDS = {
    "system.description": "1.3.6.1.2.1.1.1.0",
    "system.object_id": "1.3.6.1.2.1.1.2.0",
    "system.uptime": "1.3.6.1.2.1.1.3.0",
    "system.contact": "1.3.6.1.2.1.1.4.0",
    "system.name": "1.3.6.1.2.1.1.5.0",
    "system.location": "1.3.6.1.2.1.1.6.0",
    "system.services": "1.3.6.1.2.1.1.7.0",
}

INTERFACE_OIDS = {
    "interface.index": "1.3.6.1.2.1.2.2.1.1",
    "interface.description": "1.3.6.1.2.1.2.2.1.2",
    "interface.type": "1.3.6.1.2.1.2.2.1.3",
    "interface.mtu": "1.3.6.1.2.1.2.2.1.4",
    "interface.speed": "1.3.6.1.2.1.2.2.1.5",
    "interface.mac": "1.3.6.1.2.1.2.2.1.6",
    "interface.admin_status": "1.3.6.1.2.1.2.2.1.7",
    "interface.oper_status": "1.3.6.1.2.1.2.2.1.8",
    "interface.last_change": "1.3.6.1.2.1.2.2.1.9",
    "interface.name": "1.3.6.1.2.1.31.1.1.1.1",
    "interface.high_speed": "1.3.6.1.2.1.31.1.1.1.15",
    "interface.alias": "1.3.6.1.2.1.31.1.1.1.18",
}


class SNMPClientError(RuntimeError):
    def __init__(self, category: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.safe_message = message
        self.retryable = retryable


class SNMPTransportUnavailable(RuntimeError):
    """Compatibility error for explicitly disabled transport fixtures."""


class DisabledSNMPClient:
    def _disabled(self, *args, **kwargs):
        raise SNMPTransportUnavailable("Live SNMP transport is not available.")
    test_target = get = get_many = walk = bulk_walk = get_system_identity = get_interfaces = close = _disabled


@dataclass
class SNMPValue:
    oid: str
    value_numeric: int | float | None = None
    value_text: str | None = None
    value_type: str = "unknown"
    quality: str = "good"
    raw_ticks: int | None = None
    seconds: float | None = None
    warning: str | None = None


@dataclass
class SNMPWalkResult:
    items: list[SNMPValue]
    truncated: bool
    warning: str | None = None


AUTH_PROTOCOL_NAMES = {
    "MD5": "usmHMACMD5AuthProtocol", "SHA": "usmHMACSHAAuthProtocol",
    "SHA224": "usmHMAC128SHA224AuthProtocol",
    "SHA256": "usmHMAC192SHA256AuthProtocol",
    "SHA384": "usmHMAC256SHA384AuthProtocol",
    "SHA512": "usmHMAC384SHA512AuthProtocol",
}
PRIV_PROTOCOL_NAMES = {
    "DES": "usmDESPrivProtocol", "AES128": "usmAesCfb128Protocol",
    "AES192": "usmAesCfb192Protocol", "AES256": "usmAesCfb256Protocol",
}


def classify_error(error: Any, status: Any = None) -> SNMPClientError:
    text = f"{error or ''} {status or ''}".lower()
    if "timeout" in text or "no snmp response" in text:
        return SNMPClientError("timeout", "SNMP target did not respond before the timeout.", retryable=True)
    if "authentication" in text or "unknown user" in text or "wrong digest" in text:
        return SNMPClientError("authentication_failed", "SNMP authentication failed.")
    if "decryption" in text or "privacy" in text:
        return SNMPClientError("privacy_failed", "SNMP privacy validation failed.")
    if "authorization" in text or "noaccess" in text or "notwritable" in text:
        return SNMPClientError("access_denied", "SNMP agent denied access.")
    if "too big" in text or "toobig" in text:
        return SNMPClientError("too_big", "SNMP response exceeded agent limits.")
    if "unreachable" in text or "network is down" in text:
        return SNMPClientError("host_unreachable", "SNMP target is unreachable.", retryable=True)
    if error:
        return SNMPClientError("transport_error", "SNMP transport failed.", retryable=True)
    if status:
        return SNMPClientError("malformed_response", "SNMP agent returned an error response.")
    return SNMPClientError("unknown_error", "SNMP operation failed.")


def parse_value(oid: str, value: Any, *, max_text: int = 1000) -> SNMPValue:
    type_name = value.__class__.__name__
    if type_name in {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}:
        return SNMPValue(oid, value_type=type_name, quality="missing", warning="OID is unavailable.")
    if type_name in {"Integer", "Integer32", "Counter32", "Counter64", "Gauge32", "Unsigned32"}:
        return SNMPValue(oid, value_numeric=int(value), value_type=type_name)
    if type_name == "TimeTicks":
        ticks = int(value)
        return SNMPValue(oid, value_numeric=ticks, value_type=type_name, raw_ticks=ticks, seconds=ticks / 100)
    if type_name in {"ObjectIdentifier", "IpAddress"}:
        text = value.prettyPrint() if hasattr(value, "prettyPrint") else str(value)
        return SNMPValue(oid, value_text=text[:max_text], value_type=type_name)
    if type_name in {"Null", "NoValue"}:
        return SNMPValue(oid, value_type=type_name, quality="missing")
    if type_name in {"OctetString", "DisplayString"}:
        try:
            text = value.prettyPrint()
        except Exception:
            text = str(value)
        quality = "truncated" if len(text) > max_text else "good"
        return SNMPValue(oid, value_text=text[:max_text], value_type=type_name, quality=quality)
    try:
        text = value.prettyPrint()
    except Exception:
        text = str(value)
    return SNMPValue(
        oid, value_text=text[:max_text], value_type=type_name, quality="warning",
        warning="Unknown SNMP value type was converted to text.",
    )


class PySNMPAdapter:
    def __init__(self):
        from pysnmp.hlapi.v3arch import asyncio as hlapi
        self.hlapi = hlapi
        self.engine = hlapi.SnmpEngine()

    def auth_data(self, credential, community, auth_secret, privacy_secret):
        h = self.hlapi
        if credential.version in {"v1", "v2c"}:
            return h.CommunityData(community, mpModel=0 if credential.version == "v1" else 1)
        auth_protocol = getattr(h, AUTH_PROTOCOL_NAMES.get(credential.authentication_protocol, ""), None)
        privacy_protocol = getattr(h, PRIV_PROTOCOL_NAMES.get(credential.privacy_protocol, ""), None)
        if credential.authentication_protocol != "none" and auth_protocol is None:
            raise SNMPClientError("unsupported_protocol", "Configured authentication protocol is unsupported.")
        if credential.privacy_protocol != "none" and privacy_protocol is None:
            raise SNMPClientError("unsupported_protocol", "Configured privacy protocol is unsupported.")
        return h.UsmUserData(
            credential.username,
            authKey=auth_secret,
            privKey=privacy_secret,
            authProtocol=auth_protocol or h.usmNoAuthProtocol,
            privProtocol=privacy_protocol or h.usmNoPrivProtocol,
            securityEngineId=None,
        )

    async def target(self, host: str, port: int, timeout: float, retries: int):
        return await self.hlapi.UdpTransportTarget.create((host, port), timeout=timeout, retries=retries)

    async def get(self, auth, target, context_name: str, oids: list[str]):
        h = self.hlapi
        return await h.get_cmd(
            self.engine, auth, target, h.ContextData(contextName=context_name),
            *[h.ObjectType(h.ObjectIdentity(oid)) for oid in oids],
            lookupMib=False,
        )

    async def walk(self, auth, target, context_name: str, root: str, bulk: bool, max_repetitions: int):
        h = self.hlapi
        command = h.bulk_walk_cmd if bulk else h.walk_cmd
        kwargs = {"lookupMib": False, "lexicographicMode": False}
        if bulk:
            iterator = command(
                self.engine, auth, target, h.ContextData(contextName=context_name),
                0, max_repetitions, h.ObjectType(h.ObjectIdentity(root)), **kwargs,
            )
        else:
            iterator = command(
                self.engine, auth, target, h.ContextData(contextName=context_name),
                h.ObjectType(h.ObjectIdentity(root)), **kwargs,
            )
        async for response in iterator:
            yield response

    def close(self):
        self.engine.close_dispatcher()


class SecureSNMPClient:
    def __init__(
        self, target, credential, *, adapter=None,
        resolver: Callable[[str], list[str]] | None = None,
        authorized_networks: list[str] | None = None,
        ignored_networks: list[str] | None = None,
    ):
        self.target_config = target
        self.credential = credential
        self.adapter = adapter or PySNMPAdapter()
        self.resolver = resolver or self._resolve
        self.authorized_networks = authorized_networks or []
        self.ignored_networks = ignored_networks or []
        self._closed = False

    @staticmethod
    def _resolve(host: str) -> list[str]:
        try:
            return sorted({item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_DGRAM)})
        except socket.gaierror as error:
            raise SNMPClientError("host_unreachable", "SNMP hostname could not be resolved.") from error

    def _validate_target(self) -> str:
        if not self.target_config.enabled:
            raise SNMPClientError("configuration_error", "SNMP target is disabled.")
        if not self.credential or not self.credential.enabled:
            raise SNMPClientError("credential_missing", "Enabled SNMP credential is unavailable.")
        if self.target_config.version != self.credential.version:
            raise SNMPClientError("configuration_error", "Target and credential versions do not match.")
        if self.credential.version not in {"v1", "v2c", "v3"}:
            raise SNMPClientError("unsupported_version", "Configured SNMP version is unsupported.")
        if self.credential.version == "v1" and not settings.snmp_allow_v1:
            raise SNMPClientError("unsupported_version", "SNMPv1 is disabled by security policy.")
        if (
            self.credential.authentication_protocol == "MD5"
            or self.credential.privacy_protocol == "DES"
        ) and not settings.snmp_allow_legacy_protocols:
            raise SNMPClientError("unsupported_protocol", "Legacy SNMP security protocol is disabled.")
        if self.credential.version in {"v1", "v2c"} and not self.credential.community_encrypted:
            raise SNMPClientError("credential_missing", "SNMP community credential is unavailable.")
        if self.credential.version == "v3":
            if not self.credential.username:
                raise SNMPClientError("configuration_error", "SNMPv3 username is unavailable.")
            if self.credential.security_level == "authNoPriv" and not self.credential.authentication_secret_encrypted:
                raise SNMPClientError("credential_missing", "SNMPv3 authentication secret is unavailable.")
            if self.credential.security_level == "authPriv" and (
                not self.credential.authentication_secret_encrypted
                or not self.credential.privacy_secret_encrypted
            ):
                raise SNMPClientError("credential_missing", "SNMPv3 authentication or privacy secret is unavailable.")
        if not 1 <= self.target_config.port <= 65535:
            raise SNMPClientError("configuration_error", "SNMP target port is invalid.")
        addresses = self.resolver(self.target_config.ip_address or self.target_config.hostname)
        if not addresses:
            raise SNMPClientError("host_unreachable", "SNMP target did not resolve.")
        approved = [ipaddress.ip_network(value, strict=False) for value in self.authorized_networks]
        ignored = [ipaddress.ip_network(value, strict=False) for value in self.ignored_networks]
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                not ip.is_private or ip.is_multicast or ip.is_link_local
                or any(ip in network for network in ignored)
                or not any(ip in network for network in approved)
            ):
                raise SNMPClientError("unauthorized_target", "SNMP target is outside authorized private networks.")
        return addresses[0]

    def _secrets(self):
        try:
            return (
                SNMPSecretService.decrypt_secret(self.credential.community_encrypted)
                if self.credential.community_encrypted else None,
                SNMPSecretService.decrypt_secret(self.credential.authentication_secret_encrypted)
                if self.credential.authentication_secret_encrypted else None,
                SNMPSecretService.decrypt_secret(self.credential.privacy_secret_encrypted)
                if self.credential.privacy_secret_encrypted else None,
            )
        except SNMPSecretError as error:
            raise SNMPClientError("decryption_failed", "SNMP credential could not be decrypted.") from error

    async def _get_async(self, oids: list[str]) -> list[SNMPValue]:
        host = self._validate_target()
        community = auth_secret = privacy_secret = None
        try:
            community, auth_secret, privacy_secret = self._secrets()
            auth = self.adapter.auth_data(self.credential, community, auth_secret, privacy_secret)
            retries = min(self.target_config.retries, settings.snmp_maximum_retries)
            target = await self.adapter.target(
                host, self.target_config.port,
                min(self.target_config.timeout_seconds, 60),
                0,
            )
            bindings = []
            for attempt in range(retries + 1):
                error, status, index, bindings = await self.adapter.get(
                    auth, target, self.target_config.context_name or "", oids
                )
                if not error and not status:
                    break
                classified = classify_error(error, status)
                if not classified.retryable or attempt >= retries:
                    raise classified
                await asyncio.sleep(min(0.1 * (2 ** attempt), 0.5))
            by_oid = {str(name): parse_value(str(name), value) for name, value in bindings}
            return [by_oid.get(oid, SNMPValue(oid, quality="missing", warning="OID was not returned.")) for oid in oids]
        finally:
            community = auth_secret = privacy_secret = None

    def get(self, oid: str) -> SNMPValue:
        return self.get_many([oid])[0]

    def get_many(self, oids: list[str]) -> list[SNMPValue]:
        unique = list(dict.fromkeys(oids))
        if not unique or len(unique) > settings.snmp_maximum_oids_per_request:
            raise SNMPClientError("configuration_error", "SNMP OID request size is invalid.")
        return asyncio.run(self._get_async(unique))

    def get_system_identity(self, include_optional: bool = True) -> dict[str, SNMPValue]:
        keys = list(SYSTEM_OIDS)
        if not include_optional:
            keys = [key for key in keys if key not in {"system.contact", "system.location"}]
        values = self.get_many([SYSTEM_OIDS[key] for key in keys])
        return dict(zip(keys, values))

    async def _walk_async(
        self, root: str, *, bulk: bool, max_rows: int, max_duration: float,
        max_repetitions: int, cancelled: Callable[[], bool],
    ) -> SNMPWalkResult:
        if bulk and self.target_config.version == "v1":
            bulk = False
        host = self._validate_target()
        community = auth_secret = privacy_secret = None
        started = monotonic()
        items, seen = [], set()
        truncated = False
        try:
            community, auth_secret, privacy_secret = self._secrets()
            auth = self.adapter.auth_data(self.credential, community, auth_secret, privacy_secret)
            target = await self.adapter.target(host, self.target_config.port, self.target_config.timeout_seconds, self.target_config.retries)
            async for error, status, index, bindings in self.adapter.walk(
                auth, target, self.target_config.context_name or "", root, bulk, max_repetitions
            ):
                if cancelled():
                    raise SNMPClientError("cancelled", "SNMP walk was cancelled.")
                if monotonic() - started > max_duration:
                    return SNMPWalkResult(items, True, "Walk duration limit reached.")
                if error or status:
                    raise classify_error(error, status)
                for name, value in bindings:
                    oid = str(name)
                    if not (oid == root or oid.startswith(root + ".")):
                        return SNMPWalkResult(items, truncated)
                    if oid in seen:
                        return SNMPWalkResult(items, True, "Repeated OID stopped the walk.")
                    seen.add(oid)
                    items.append(parse_value(oid, value))
                    if len(items) >= max_rows:
                        return SNMPWalkResult(items, True, "Walk row limit reached.")
            return SNMPWalkResult(items, truncated)
        finally:
            community = auth_secret = privacy_secret = None

    def walk(self, root: str, *, max_rows=100, max_duration=30, cancelled=lambda: False):
        return asyncio.run(self._walk_async(root, bulk=False, max_rows=min(max_rows, settings.snmp_maximum_walk_rows), max_duration=min(max_duration, 60), max_repetitions=1, cancelled=cancelled))

    def bulk_walk(self, root: str, *, max_rows=100, max_duration=30, max_repetitions=20, cancelled=lambda: False):
        return asyncio.run(self._walk_async(root, bulk=True, max_rows=min(max_rows, settings.snmp_maximum_walk_rows), max_duration=min(max_duration, 60), max_repetitions=min(max(1, max_repetitions), 50), cancelled=cancelled))

    def get_interfaces_preview(self, *, max_interfaces: int, cancelled=lambda: False):
        results = {}
        for key, root in INTERFACE_OIDS.items():
            results[key] = self.bulk_walk(root, max_rows=max_interfaces, cancelled=cancelled)
        return results

    def test_target(self, include_optional_identity: bool = True):
        started = monotonic()
        identity = self.get_system_identity(include_optional_identity)
        return {
            "status": "success",
            "transport_status": "success",
            "authentication_status": "success",
            "system_identity_status": "partial" if any(v.quality != "good" for v in identity.values()) else "success",
            "detected_version": self.target_config.version,
            "response_time_ms": round((monotonic() - started) * 1000, 2),
            "identity": identity,
            "warnings": [v.warning for v in identity.values() if v.warning],
            "tested_at": datetime.now(timezone.utc),
        }

    def close(self):
        if not self._closed:
            self.adapter.close()
            self._closed = True
