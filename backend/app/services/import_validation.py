import ipaddress
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.discovery.network import normalize_mac


CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    normalized_value: Any = None
    code: str | None = None
    message: str | None = None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).replace("“", '"').replace("”", '"').replace("’", "'")
    text = " ".join(text.strip().split())
    return text or None


class ImportFieldValidator(ABC):
    @abstractmethod
    def validate(self, value: Any) -> ValidationResult: ...


class TextValidator(ImportFieldValidator):
    def __init__(self, maximum: int, *, required: bool = False) -> None:
        self.maximum, self.required = maximum, required

    def validate(self, value: Any) -> ValidationResult:
        text = clean_text(value)
        if text is None:
            return ValidationResult(not self.required, None, "required" if self.required else None, "Value is required" if self.required else None)
        if CONTROL.search(text):
            return ValidationResult(False, None, "control_character", "Control characters are not allowed")
        if len(text) > self.maximum:
            return ValidationResult(False, None, "too_long", f"Value exceeds {self.maximum} characters")
        return ValidationResult(True, text)


class IPAddressValidator(ImportFieldValidator):
    def validate(self, value: Any) -> ValidationResult:
        text = clean_text(value)
        if text is None:
            return ValidationResult(True, None)
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return ValidationResult(False, None, "invalid_ipv4", "Enter a valid IPv4 address")
        if address.version != 4:
            return ValidationResult(False, None, "invalid_ipv4", "Only IPv4 addresses are supported")
        return ValidationResult(True, str(address))


class MACAddressValidator(ImportFieldValidator):
    def validate(self, value: Any) -> ValidationResult:
        text = clean_text(value)
        if text is None:
            return ValidationResult(True, None)
        normalized = normalize_mac(text)
        if not normalized:
            return ValidationResult(False, None, "invalid_mac", "Enter a valid 48-bit MAC address")
        return ValidationResult(True, normalized)


class AssetTagValidator(TextValidator):
    def __init__(self) -> None:
        super().__init__(100, required=True)

    def validate(self, value: Any) -> ValidationResult:
        result = super().validate(value)
        if result.valid and result.normalized_value and not re.fullmatch(r"[A-Za-z0-9._/\-]+", result.normalized_value):
            return ValidationResult(False, None, "invalid_asset_tag", "Asset tag contains unsupported characters")
        return result


class HostnameValidator(TextValidator):
    def __init__(self) -> None:
        super().__init__(255, required=True)

    def validate(self, value: Any) -> ValidationResult:
        result = super().validate(value)
        if not result.valid or not result.normalized_value:
            return result
        hostname = result.normalized_value.rstrip(".").lower()
        if len(hostname) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in hostname.split(".")):
            return ValidationResult(False, None, "invalid_hostname", "Hostname structure is invalid")
        return ValidationResult(True, hostname)


class DepartmentValidator(TextValidator):
    def __init__(self) -> None: super().__init__(120)


class BuildingValidator(TextValidator):
    def __init__(self) -> None: super().__init__(120)


class FloorValidator(TextValidator):
    def __init__(self) -> None: super().__init__(120)


class RoomValidator(TextValidator):
    def __init__(self) -> None: super().__init__(120)


class InventoryStatusValidator(ImportFieldValidator):
    ALIASES = {"active": "Active", "in service": "Active", "inactive": "Inactive", "retired": "Retired", "disposed": "Retired"}

    def validate(self, value: Any) -> ValidationResult:
        text = clean_text(value)
        if text is None:
            return ValidationResult(True, None)
        normalized = self.ALIASES.get(text.lower())
        if not normalized:
            return ValidationResult(False, None, "invalid_inventory_status", "Inventory status must be Active, Inactive, or Retired")
        return ValidationResult(True, normalized)


VALIDATORS: dict[str, ImportFieldValidator] = {
    "asset_tag": AssetTagValidator(), "hostname": HostnameValidator(),
    "ip_address": IPAddressValidator(), "mac_address": MACAddressValidator(),
    "department_name": DepartmentValidator(), "building_name": BuildingValidator(),
    "floor_name": FloorValidator(), "room_name": RoomValidator(),
    "network_zone": TextValidator(120), "vendor": TextValidator(128), "brand": TextValidator(128),
    "model": TextValidator(128), "serial_number": TextValidator(128),
    "inventory_status": InventoryStatusValidator(), "notes": TextValidator(2000),
}


def validate_row(raw: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any], list[dict], list[dict]]:
    normalized: dict[str, Any] = {}
    errors: list[dict] = []
    warnings: list[dict] = []
    source_by_target = {target: source for source, target in mapping.items()}
    for field, validator in VALIDATORS.items():
        source = source_by_target.get(field)
        result = validator.validate(raw.get(source) if source else None)
        normalized[field] = result.normalized_value
        if not result.valid:
            errors.append({"field": field, "code": result.code, "message": result.message, "original_value": clean_text(raw.get(source)) if source else None})
    return normalized, errors, warnings
