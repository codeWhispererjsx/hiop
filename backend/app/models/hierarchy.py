import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class NamedEntity:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Property(NamedEntity, Base):
    __tablename__ = "properties"
    code: Mapped[str | None] = mapped_column(String(40), unique=True)
    address: Mapped[str | None] = mapped_column(String(255))


class Building(NamedEntity, Base):
    __tablename__ = "buildings"
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), index=True)


class Floor(NamedEntity, Base):
    __tablename__ = "floors"
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True)


class Room(NamedEntity, Base):
    __tablename__ = "rooms"
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id", ondelete="RESTRICT"), index=True)


class Department(NamedEntity, Base):
    __tablename__ = "departments"
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), index=True)


class NetworkZone(NamedEntity, Base):
    __tablename__ = "network_zones"
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    cidr: Mapped[str | None] = mapped_column(String(64))
    vlan_id: Mapped[int | None] = mapped_column(Integer)


for entity in (Property, Building, Floor, Room, Department, NetworkZone):
    Index(f"uq_{entity.__tablename__}_name_lower", func.lower(entity.name), unique=True)

Index("uq_network_zones_cidr", NetworkZone.cidr, unique=True, postgresql_where=NetworkZone.cidr.is_not(None))
