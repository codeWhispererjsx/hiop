import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class AssetProcurement(Base):
    __tablename__="asset_procurements"
    __table_args__=(UniqueConstraint("procurement_number",name="uq_asset_procurement_number"),Index("ix_asset_procurement_org_status","organization_id","status"),CheckConstraint("status IN ('draft','requested','approved','ordered','partially_received','received','cancelled')",name="ck_asset_procurement_status"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    organization_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("organizations.id",ondelete="RESTRICT"),nullable=False,index=True)
    property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id",ondelete="RESTRICT"),index=True)
    procurement_number:Mapped[str]=mapped_column(String(24),nullable=False)
    reference_number:Mapped[str|None]=mapped_column(String(80),index=True)
    title:Mapped[str]=mapped_column(String(220),nullable=False)
    description:Mapped[str|None]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(30),nullable=False,default="draft",server_default="draft")
    requested_date:Mapped[date|None]=mapped_column(Date)
    approved_date:Mapped[date|None]=mapped_column(Date)
    ordered_date:Mapped[date|None]=mapped_column(Date)
    expected_delivery_date:Mapped[date|None]=mapped_column(Date)
    received_date:Mapped[date|None]=mapped_column(Date)
    department_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("departments.id",ondelete="SET NULL"),index=True)
    vendor_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id",ondelete="SET NULL"),index=True)
    requested_by:Mapped[str]=mapped_column(String,ForeignKey("users.id",ondelete="RESTRICT"),nullable=False,index=True)
    approved_by:Mapped[str|None]=mapped_column(String,ForeignKey("users.id",ondelete="SET NULL"))
    currency:Mapped[str]=mapped_column(String(3),nullable=False,default="NGN",server_default="NGN")
    notes:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now(),onupdate=func.now())

class ProcurementLineItem(Base):
    __tablename__="procurement_line_items"
    __table_args__=(CheckConstraint("quantity_requested > 0",name="ck_procurement_item_quantity"),CheckConstraint("quantity_received >= 0 AND quantity_received <= quantity_requested",name="ck_procurement_item_received"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    procurement_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_procurements.id",ondelete="CASCADE"),nullable=False,index=True)
    description:Mapped[str]=mapped_column(String(500),nullable=False)
    device_type:Mapped[str]=mapped_column(String(80),nullable=False,default="Other",server_default="Other")
    quantity_requested:Mapped[int]=mapped_column(Integer,nullable=False)
    quantity_received:Mapped[int]=mapped_column(Integer,nullable=False,default=0,server_default="0")
    unit_cost:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False,default=0,server_default="0")

class ProcurementAssetLink(Base):
    __tablename__="procurement_asset_links"
    __table_args__=(UniqueConstraint("asset_id",name="uq_procurement_asset_link_asset"),UniqueConstraint("procurement_id","asset_id",name="uq_procurement_asset_link"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    procurement_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_procurements.id",ondelete="CASCADE"),nullable=False,index=True)
    line_item_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("procurement_line_items.id",ondelete="SET NULL"))
    asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("managed_assets.id",ondelete="RESTRICT"),nullable=False,index=True)
    linked_by:Mapped[str|None]=mapped_column(String,ForeignKey("users.id",ondelete="SET NULL"))
    linked_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class ProcurementEvent(Base):
    __tablename__="procurement_events"
    __table_args__=(Index("ix_procurement_events_record_created","procurement_id","created_at"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    procurement_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_procurements.id",ondelete="CASCADE"),nullable=False)
    organization_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("organizations.id",ondelete="RESTRICT"),nullable=False,index=True)
    action:Mapped[str]=mapped_column(String(40),nullable=False)
    previous_status:Mapped[str|None]=mapped_column(String(30))
    new_status:Mapped[str]=mapped_column(String(30),nullable=False)
    actor_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id",ondelete="SET NULL"))
    actor_name:Mapped[str]=mapped_column(String(180),nullable=False)
    notes:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
