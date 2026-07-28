import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
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
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    type: Mapped[str] = mapped_column(String(40), default="hotel", server_default="hotel", nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC", nullable=False)
    number_of_rooms: Mapped[int | None] = mapped_column(Integer)
    number_of_floors: Mapped[int | None] = mapped_column(Integer)
    operational_status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(40), default="hospitality_group", server_default="hospitality_group", nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC", nullable=False)
    logo: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


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
