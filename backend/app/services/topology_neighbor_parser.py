"""Strict normalization for approved LLDP-MIB and Cisco CDP cache rows."""
import hashlib
import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

LLDP_OIDS = {
    "local_chassis_subtype": "1.0.8802.1.1.2.1.3.1.0",
    "local_chassis_id": "1.0.8802.1.1.2.1.3.2.0",
    "local_system_name": "1.0.8802.1.1.2.1.3.3.0",
    "local_system_description": "1.0.8802.1.1.2.1.3.4.0",
    "local_capabilities": "1.0.8802.1.1.2.1.3.5.0",
    "local_port_subtype": "1.0.8802.1.1.2.1.3.7.1.2",
    "local_port_id": "1.0.8802.1.1.2.1.3.7.1.3",
    "local_port_description": "1.0.8802.1.1.2.1.3.7.1.4",
    "remote_chassis_subtype": "1.0.8802.1.1.2.1.4.1.1.4",
    "remote_chassis_id": "1.0.8802.1.1.2.1.4.1.1.5",
    "remote_port_subtype": "1.0.8802.1.1.2.1.4.1.1.6",
    "remote_port_id": "1.0.8802.1.1.2.1.4.1.1.7",
    "remote_port_description": "1.0.8802.1.1.2.1.4.1.1.8",
    "remote_system_name": "1.0.8802.1.1.2.1.4.1.1.9",
    "remote_system_description": "1.0.8802.1.1.2.1.4.1.1.10",
    "remote_capabilities": "1.0.8802.1.1.2.1.4.1.1.12",
    "remote_management_address": "1.0.8802.1.1.2.1.4.2.1.4",
}
CDP_OIDS = {
    "address_type": "1.3.6.1.4.1.9.9.23.1.2.1.1.3",
    "remote_management_address": "1.3.6.1.4.1.9.9.23.1.2.1.1.4",
    "remote_system_description": "1.3.6.1.4.1.9.9.23.1.2.1.1.5",
    "remote_system_name": "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
    "remote_port_id": "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
    "remote_platform": "1.3.6.1.4.1.9.9.23.1.2.1.1.8",
    "remote_capabilities": "1.3.6.1.4.1.9.9.23.1.2.1.1.9",
    "native_vlan": "1.3.6.1.4.1.9.9.23.1.2.1.1.11",
    "duplex": "1.3.6.1.4.1.9.9.23.1.2.1.1.12",
}

LLDP_CAPABILITIES = {
    0: "other", 1: "repeater", 2: "bridge", 3: "wlan_access_point",
    4: "router", 5: "telephone", 6: "docsis", 7: "station_only",
    8: "cvlan", 9: "svlan", 10: "two_port_mac_relay",
}
CDP_CAPABILITIES = {
    0: "router", 1: "transparent_bridge", 2: "source_route_bridge",
    3: "switch", 4: "host", 5: "igmp", 6: "repeater", 7: "phone",
}


@dataclass
class NormalizedNeighbor:
    protocol: str
    local_port_identifier: str
    local_ifindex: int | None = None
    local_port_description: str | None = None
    remote_chassis_id: str | None = None
    remote_chassis_subtype: str | None = None
    remote_port_id: str | None = None
    remote_port_subtype: str | None = None
    remote_port_description: str | None = None
    remote_system_name: str | None = None
    remote_system_description: str | None = None
    remote_management_address: str | None = None
    remote_capabilities: list[str] = field(default_factory=list)
    remote_platform: str | None = None
    native_vlan: int | None = None
    duplex: str | None = None
    raw_index: str | None = None
    identity_key: str = ""
    warnings: list[str] = field(default_factory=list)


def safe_text(value: Any, maximum: int = 1000) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = "".join(ch for ch in str(value).strip() if ch.isprintable())
    return value[:maximum] or None


def normalize_mac(value: Any) -> str | None:
    text = safe_text(value, 255)
    if not text:
        return None
    compact = re.sub(r"[^0-9a-fA-F]", "", text)
    if len(compact) == 12:
        return ":".join(compact[i:i + 2] for i in range(0, 12, 2)).lower()
    return text.lower()


def normalize_ip(value: Any) -> str | None:
    text = safe_text(value, 100)
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        if isinstance(value, (bytes, bytearray)) and len(value) in (4, 16):
            return str(ipaddress.ip_address(value))
        return None


def capability_bits(value: Any, mapping: dict[int, str]) -> list[str]:
    if isinstance(value, list):
        return sorted({safe_text(item, 50) for item in value if safe_text(item, 50)})
    if isinstance(value, bytes):
        return [
            name for bit, name in mapping.items()
            if bit // 8 < len(value) and value[bit // 8] & (0x80 >> (bit % 8))
        ]
    else:
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            return []
    return [name for bit, name in mapping.items() if number & (1 << bit)]


def remote_identity(row: dict[str, Any]) -> str:
    chassis = normalize_mac(row.get("remote_chassis_id"))
    address = normalize_ip(row.get("remote_management_address"))
    name = (safe_text(row.get("remote_system_name"), 255) or "").lower()
    port = (safe_text(row.get("remote_port_id"), 255) or "").lower()
    if chassis:
        raw = f"chassis:{chassis}"
    elif address:
        raw = f"address:{address}"
    elif name and address:
        raw = f"name-address:{name}:{address}"
    elif name and port:
        raw = f"name-port:{name}:{port}"
    elif name:
        raw = f"weak-name:{name}:{port}"
    else:
        raw = f"protocol:{safe_text(row.get('protocol_identifier'), 255) or port}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_rows(rows: Iterable[dict[str, Any]], protocol: str, maximum: int) -> tuple[list[NormalizedNeighbor], list[str]]:
    parsed, warnings = [], []
    for position, source in enumerate(rows):
        if position >= maximum:
            warnings.append(f"{protocol.upper()} neighbor limit reached.")
            break
        local_id = safe_text(source.get("local_port_identifier") or source.get("local_ifindex"), 255)
        if not local_id:
            warnings.append(f"Skipped {protocol.upper()} row without a local port.")
            continue
        chassis = normalize_mac(source.get("remote_chassis_id"))
        name = safe_text(source.get("remote_system_name"), 255)
        address = normalize_ip(source.get("remote_management_address"))
        port = safe_text(source.get("remote_port_id"), 255)
        if not any((chassis, name, address)):
            warnings.append(f"Skipped {protocol.upper()} row without a safe remote identity.")
            continue
        mapping = LLDP_CAPABILITIES if protocol == "lldp" else CDP_CAPABILITIES
        neighbor = NormalizedNeighbor(
            protocol=protocol, local_port_identifier=local_id,
            local_ifindex=int(source["local_ifindex"]) if str(source.get("local_ifindex", "")).isdigit() else None,
            local_port_description=safe_text(source.get("local_port_description"), 500),
            remote_chassis_id=chassis,
            remote_chassis_subtype=safe_text(source.get("remote_chassis_subtype"), 40),
            remote_port_id=port, remote_port_subtype=safe_text(source.get("remote_port_subtype"), 40),
            remote_port_description=safe_text(source.get("remote_port_description"), 500),
            remote_system_name=name,
            remote_system_description=safe_text(source.get("remote_system_description"), 1000),
            remote_management_address=address,
            remote_capabilities=capability_bits(source.get("remote_capabilities"), mapping),
            remote_platform=safe_text(source.get("remote_platform"), 255),
            native_vlan=int(source["native_vlan"]) if str(source.get("native_vlan", "")).isdigit() else None,
            duplex=safe_text(source.get("duplex"), 20), raw_index=safe_text(source.get("raw_index"), 255),
        )
        neighbor.identity_key = remote_identity({**source, "remote_chassis_id": chassis, "protocol_identifier": name or port})
        parsed.append(neighbor)
    return parsed, warnings


def parse_lldp_rows(rows: Iterable[dict[str, Any]], maximum: int = 500):
    return _parse_rows(rows, "lldp", maximum)


def parse_cdp_rows(rows: Iterable[dict[str, Any]], maximum: int = 500):
    return _parse_rows(rows, "cdp", maximum)


def tabular_walks(walks: dict[str, Any], oid_map: dict[str, str], protocol: str) -> list[dict[str, Any]]:
    """Join bounded column walks by their protocol-specific composite index."""
    rows: dict[str, dict[str, Any]] = {}
    for field_name, result in walks.items():
        root = oid_map[field_name]
        for item in result.items:
            suffix = item.oid.removeprefix(root + ".")
            value = item.value_numeric if item.value_numeric is not None else item.value_text
            row = rows.setdefault(suffix, {"raw_index": suffix})
            row[field_name] = value
    for index, row in rows.items():
        parts = index.split(".")
        if protocol == "lldp" and len(parts) >= 3:
            row.setdefault("local_port_identifier", parts[-2])
        elif protocol == "cdp" and parts:
            row.setdefault("local_ifindex", parts[0])
            row.setdefault("local_port_identifier", parts[0])
    return list(rows.values())
