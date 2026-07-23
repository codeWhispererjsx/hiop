import re
import unicodedata


CANONICAL_FIELDS = (
    "asset_tag", "hostname", "ip_address", "mac_address", "department_name",
    "building_name", "floor_name", "room_name", "network_zone", "vendor",
    "brand", "model", "device_type", "serial_number", "inventory_status", "notes",
)
REQUIRED_FIELDS = {"asset_tag", "hostname"}

ALIASES = {
    "asset_tag": {"asset tag", "asset_tag", "asset id", "asset number", "tag number"},
    "hostname": {"hostname", "host name", "computer name", "device name", "machine name"},
    "ip_address": {"ip", "ip address", "ip_address", "ipv4"},
    "mac_address": {"mac", "mac address", "mac_address", "physical address"},
    "department_name": {"department", "department name", "dept"},
    "building_name": {"building", "building name", "tower"},
    "floor_name": {"floor", "floor name", "level"},
    "room_name": {"room", "room name", "location", "area"},
    "network_zone": {"network zone", "zone", "vlan", "subnet group"},
    "vendor": {"vendor", "manufacturer", "maker"},
    "brand": {"brand"},
    "model": {"model", "model number"},
    "device_type": {"device type", "device_type", "asset type", "equipment type"},
    "serial_number": {"serial", "serial number", "service tag"},
    "inventory_status": {"inventory status", "status", "asset status"},
    "notes": {"notes", "comments", "description"},
}


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"\s+", " ", text.replace("-", " "))


ALIAS_LOOKUP = {normalize_header(alias): field for field, aliases in ALIASES.items() for alias in aliases}


def detect_mapping(headers: list[str]) -> dict:
    suggested: dict[str, str | None] = {}
    canonical_sources: dict[str, list[str]] = {}
    unknown: list[str] = []
    for header in headers:
        canonical = ALIAS_LOOKUP.get(normalize_header(header))
        suggested[header] = canonical
        if canonical:
            canonical_sources.setdefault(canonical, []).append(header)
        else:
            unknown.append(header)
    ambiguous = {key: value for key, value in canonical_sources.items() if len(value) > 1}
    mapped = {value for value in suggested.values() if value and value not in ambiguous}
    return {
        "headers": headers,
        "suggested_mapping": suggested,
        "unknown_columns": unknown,
        "ambiguous_mappings": ambiguous,
        "missing_required_columns": sorted(REQUIRED_FIELDS - mapped),
    }


def validate_mapping(headers: list[str], mapping: dict[str, str | None]) -> dict[str, str]:
    unknown_sources = set(mapping) - set(headers)
    if unknown_sources:
        raise ValueError("Mapping contains columns that are not present in the file")
    cleaned = {source: target for source, target in mapping.items() if target}
    if any(target not in CANONICAL_FIELDS for target in cleaned.values()):
        raise ValueError("Mapping contains an unsupported canonical field")
    targets = list(cleaned.values())
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        raise ValueError(f"Multiple columns map to: {', '.join(duplicates)}")
    missing = REQUIRED_FIELDS - set(targets)
    if missing:
        raise ValueError(f"Required fields are not mapped: {', '.join(sorted(missing))}")
    return cleaned
