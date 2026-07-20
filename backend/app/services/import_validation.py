from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    normalized_value: Any = None
    message: str | None = None


class ImportFieldValidator(ABC):
    """Interface implemented by field validators in a later import phase."""

    @abstractmethod
    def validate(self, value: Any) -> ValidationResult:
        raise NotImplementedError


class IPAddressValidator(ImportFieldValidator):
    pass


class MACAddressValidator(ImportFieldValidator):
    pass


class AssetTagValidator(ImportFieldValidator):
    pass


class HostnameValidator(ImportFieldValidator):
    pass


class DepartmentValidator(ImportFieldValidator):
    pass


class BuildingValidator(ImportFieldValidator):
    pass


class FloorValidator(ImportFieldValidator):
    pass


class RoomValidator(ImportFieldValidator):
    pass
