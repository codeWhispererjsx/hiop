from uuid import UUID

from ipaddress import ip_network

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HierarchyBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True


class PropertyInput(HierarchyBase):
    code: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)


class PropertyResponse(PropertyInput):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class ParentInput(HierarchyBase):
    parent_id: UUID | None = None


class HierarchyResponse(HierarchyBase):
    id: UUID
    parent_id: UUID | None = None
    model_config = ConfigDict(from_attributes=True)


class NetworkZoneInput(ParentInput):
    cidr: str | None = Field(default=None, max_length=64)
    vlan_id: int | None = Field(default=None, ge=1, le=4094)

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return str(ip_network(value.strip(), strict=False))
        except ValueError as exc:
            raise ValueError("Enter a valid IPv4 or IPv6 CIDR range") from exc


class NetworkZoneResponse(NetworkZoneInput):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class HierarchyMutation(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True
    parent_id: UUID | None = None
    code: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    cidr: str | None = Field(default=None, max_length=64)
    vlan_id: int | None = Field(default=None, ge=1, le=4094)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class HierarchyCatalog(BaseModel):
    properties: list[PropertyResponse]
    buildings: list[HierarchyResponse]
    floors: list[HierarchyResponse]
    rooms: list[HierarchyResponse]
    departments: list[HierarchyResponse]
    network_zones: list[NetworkZoneResponse]
