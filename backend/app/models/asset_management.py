import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base

def uid(): return mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
def now(): return mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
def money(default="0"): return mapped_column(Numeric(18,2),default=Decimal(default),server_default=default)

class AssetCategory(Base):
    __tablename__="asset_categories"; id:Mapped[uuid.UUID]=uid(); name:Mapped[str]=mapped_column(String(120),unique=True); code:Mapped[str]=mapped_column(String(50),unique=True); description:Mapped[str|None]=mapped_column(Text); enabled:Mapped[bool]=mapped_column(Boolean,default=True,server_default="true")
class AssetSubcategory(Base):
    __tablename__="asset_subcategories"; id:Mapped[uuid.UUID]=uid(); category_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_categories.id"),index=True); name:Mapped[str]=mapped_column(String(120)); code:Mapped[str]=mapped_column(String(50),unique=True); useful_life_months:Mapped[int|None]=mapped_column(Integer); __table_args__=(UniqueConstraint("category_id","name",name="uq_asset_subcategory_name"),)
class AssetStatus(Base):
    __tablename__="asset_statuses"; id:Mapped[uuid.UUID]=uid(); name:Mapped[str]=mapped_column(String(60),unique=True); code:Mapped[str]=mapped_column(String(40),unique=True); operational:Mapped[bool]=mapped_column(Boolean,default=False); terminal:Mapped[bool]=mapped_column(Boolean,default=False)
class AssetOwnership(Base):
    __tablename__="asset_ownerships"; id:Mapped[uuid.UUID]=uid(); name:Mapped[str]=mapped_column(String(80),unique=True); code:Mapped[str]=mapped_column(String(40),unique=True); description:Mapped[str|None]=mapped_column(Text)
class EnterpriseAsset(Base):
    __tablename__="enterprise_assets"
    id:Mapped[uuid.UUID]=uid(); asset_number:Mapped[str]=mapped_column(String(32),unique=True,index=True); asset_tag:Mapped[str|None]=mapped_column(String(100),unique=True,index=True); barcode:Mapped[str|None]=mapped_column(String(180),unique=True); qr_code:Mapped[str|None]=mapped_column(String(500),unique=True); serial_number:Mapped[str|None]=mapped_column(String(180),index=True); manufacturer:Mapped[str|None]=mapped_column(String(160)); model:Mapped[str|None]=mapped_column(String(160)); description:Mapped[str|None]=mapped_column(Text)
    category_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_categories.id")); subcategory_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_subcategories.id")); ownership_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_ownerships.id")); legacy_device_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("devices.id")); ci_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("configuration_items.id"),index=True)
    purchase_date:Mapped[date|None]=mapped_column(Date); purchase_cost:Mapped[Decimal]=money(); current_value:Mapped[Decimal]=money(); residual_value:Mapped[Decimal]=money(); depreciation_method:Mapped[str]=mapped_column(String(30),default="straight_line"); depreciation_value:Mapped[Decimal]=money(); useful_life_months:Mapped[int]=mapped_column(Integer,default=60); warranty_start:Mapped[date|None]=mapped_column(Date); warranty_end:Mapped[date|None]=mapped_column(Date,index=True); end_of_life:Mapped[date|None]=mapped_column(Date,index=True)
    owner_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); assigned_user_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); department_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("departments.id")); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id"),index=True); building_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("buildings.id")); floor_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("floors.id")); room_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("rooms.id")); rack_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True)); status:Mapped[str]=mapped_column(String(40),default="planned",index=True); lifecycle_stage:Mapped[str]=mapped_column(String(40),default="planned",index=True); version:Mapped[int]=mapped_column(Integer,default=1); created_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); created_at:Mapped[datetime]=now(); updated_at:Mapped[datetime]=now(); __table_args__=(Index("ix_enterprise_assets_property_lifecycle","property_id","lifecycle_stage"),)
class AssetLifecycle(Base):
    __tablename__="asset_lifecycle_history"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id",ondelete="CASCADE"),index=True); previous_stage:Mapped[str|None]=mapped_column(String(40)); current_stage:Mapped[str]=mapped_column(String(40)); reason:Mapped[str]=mapped_column(String(1000)); actor_id:Mapped[str]=mapped_column(String,ForeignKey("users.id")); occurred_at:Mapped[datetime]=now()
class AssetLocationHistory(Base):
    __tablename__="asset_location_history"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id",ondelete="CASCADE"),index=True); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id")); building_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("buildings.id")); floor_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("floors.id")); room_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("rooms.id")); rack_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True)); reason:Mapped[str]=mapped_column(String(500)); effective_at:Mapped[datetime]=now()
class AssetAssignment(Base):
    __tablename__="asset_assignments"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id",ondelete="CASCADE"),index=True); user_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); department_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("departments.id")); assigned_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); assigned_at:Mapped[datetime]=now(); returned_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); notes:Mapped[str|None]=mapped_column(Text)
class AssetTransfer(Base):
    __tablename__="asset_transfers"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id"),index=True); from_property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id")); to_property_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id")); status:Mapped[str]=mapped_column(String(30),default="requested"); reason:Mapped[str]=mapped_column(Text); requested_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); approved_by:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); transferred_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=now()
class AssetDisposal(Base):
    __tablename__="asset_disposals"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id"),unique=True); method:Mapped[str]=mapped_column(String(60)); reason:Mapped[str]=mapped_column(Text); proceeds:Mapped[Decimal]=money(); data_destruction_evidence:Mapped[str|None]=mapped_column(Text); approved_by:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); disposed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=now()

class VendorCategory(Base):
    __tablename__="vendor_categories"; id:Mapped[uuid.UUID]=uid(); name:Mapped[str]=mapped_column(String(100),unique=True); code:Mapped[str]=mapped_column(String(40),unique=True)
class Vendor(Base):
    __tablename__="vendors"
    id:Mapped[uuid.UUID]=uid()
    vendor_number:Mapped[str]=mapped_column(String(32),unique=True,index=True)
    organization_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("organizations.id",ondelete="RESTRICT"),nullable=False,index=True)
    legal_name:Mapped[str]=mapped_column(String(220),index=True)
    trading_name:Mapped[str|None]=mapped_column(String(220))
    vendor_code:Mapped[str|None]=mapped_column(String(40))
    vendor_type:Mapped[str]=mapped_column(String(30),default="other",server_default="other",index=True)
    description:Mapped[str|None]=mapped_column(Text)
    website:Mapped[str|None]=mapped_column(String(500))
    primary_email:Mapped[str|None]=mapped_column(String(255))
    primary_phone:Mapped[str|None]=mapped_column(String(80))
    address:Mapped[str|None]=mapped_column(Text)
    country:Mapped[str|None]=mapped_column(String(100))
    notes:Mapped[str|None]=mapped_column(Text)
    support_agreement_reference:Mapped[str|None]=mapped_column(String(120))
    renewal_date:Mapped[date|None]=mapped_column(Date)
    products_services:Mapped[str]=mapped_column(Text,default="[]",server_default="[]")
    category_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("vendor_categories.id"))
    preferred:Mapped[bool]=mapped_column(Boolean,default=False)
    approved:Mapped[bool]=mapped_column(Boolean,default=False)
    tax_id:Mapped[str|None]=mapped_column(String(100))
    service_regions:Mapped[str]=mapped_column(Text,default="[]")
    rating:Mapped[Decimal]=mapped_column(Numeric(4,2),default=0)
    status:Mapped[str]=mapped_column(String(30),default="active",server_default="active",index=True)
    created_by:Mapped[str]=mapped_column(String,ForeignKey("users.id"))
    created_at:Mapped[datetime]=now()
    updated_at:Mapped[datetime]=now()
class VendorContact(Base):
    __tablename__="vendor_contacts"
    id:Mapped[uuid.UUID]=uid()
    vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id",ondelete="CASCADE"),index=True)
    name:Mapped[str]=mapped_column(String(160))
    role:Mapped[str]=mapped_column(String(100),default="support")
    email:Mapped[str|None]=mapped_column(String(255))
    phone:Mapped[str|None]=mapped_column(String(80))
    department:Mapped[str|None]=mapped_column(String(120))
    notes:Mapped[str|None]=mapped_column(Text)
    escalation_level:Mapped[int]=mapped_column(Integer,default=0)
    primary:Mapped[bool]=mapped_column(Boolean,default=False)
    updated_at:Mapped[datetime]=now()
class VendorLocation(Base):
    __tablename__="vendor_locations"; id:Mapped[uuid.UUID]=uid(); vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id",ondelete="CASCADE"),index=True); name:Mapped[str]=mapped_column(String(160)); address:Mapped[str]=mapped_column(Text); region:Mapped[str|None]=mapped_column(String(100)); country:Mapped[str|None]=mapped_column(String(80))
class VendorPerformance(Base):
    __tablename__="vendor_performance"; id:Mapped[uuid.UUID]=uid(); vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id",ondelete="CASCADE"),index=True); period_start:Mapped[date]=mapped_column(Date); period_end:Mapped[date]=mapped_column(Date); delivery_score:Mapped[int]=mapped_column(Integer); quality_score:Mapped[int]=mapped_column(Integer); support_score:Mapped[int]=mapped_column(Integer); compliance_score:Mapped[int]=mapped_column(Integer); overall_score:Mapped[Decimal]=mapped_column(Numeric(5,2)); calculated_at:Mapped[datetime]=now()
class VendorReview(Base):
    __tablename__="vendor_reviews"; id:Mapped[uuid.UUID]=uid(); vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id"),index=True); rating:Mapped[int]=mapped_column(Integer); findings:Mapped[str]=mapped_column(Text); recommendation:Mapped[str|None]=mapped_column(Text); reviewed_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); reviewed_at:Mapped[datetime]=now()
class VendorCertification(Base):
    __tablename__="vendor_certifications"; id:Mapped[uuid.UUID]=uid(); vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id"),index=True); name:Mapped[str]=mapped_column(String(180)); issuer:Mapped[str|None]=mapped_column(String(180)); certificate_number:Mapped[str|None]=mapped_column(String(120)); valid_from:Mapped[date|None]=mapped_column(Date); valid_until:Mapped[date|None]=mapped_column(Date,index=True); attachment_ref:Mapped[str|None]=mapped_column(String(500))

class ProcurementBudget(Base):
    __tablename__="procurement_budgets"; id:Mapped[uuid.UUID]=uid(); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id"),index=True); department_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("departments.id")); fiscal_year:Mapped[int]=mapped_column(Integer); currency:Mapped[str]=mapped_column(String(3),default="USD"); allocated:Mapped[Decimal]=money(); committed:Mapped[Decimal]=money(); spent:Mapped[Decimal]=money(); __table_args__=(UniqueConstraint("property_id","department_id","fiscal_year",name="uq_procurement_budget_scope"),)
class PurchaseRequest(Base):
    __tablename__="purchase_requests"; id:Mapped[uuid.UUID]=uid(); request_number:Mapped[str]=mapped_column(String(32),unique=True,index=True); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id"),index=True); department_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("departments.id")); budget_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("procurement_budgets.id")); title:Mapped[str]=mapped_column(String(220)); justification:Mapped[str]=mapped_column(Text); requested_amount:Mapped[Decimal]=money(); currency:Mapped[str]=mapped_column(String(3),default="USD"); status:Mapped[str]=mapped_column(String(30),default="draft",index=True); requested_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); created_at:Mapped[datetime]=now(); updated_at:Mapped[datetime]=now()
class ProcurementApproval(Base):
    __tablename__="procurement_approvals"; id:Mapped[uuid.UUID]=uid(); purchase_request_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("purchase_requests.id",ondelete="CASCADE"),index=True); sequence:Mapped[int]=mapped_column(Integer); approver_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); status:Mapped[str]=mapped_column(String(30),default="pending"); decision_notes:Mapped[str|None]=mapped_column(Text); decided_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); __table_args__=(UniqueConstraint("purchase_request_id","sequence",name="uq_procurement_approval_sequence"),)
class PurchaseOrder(Base):
    __tablename__="purchase_orders"; id:Mapped[uuid.UUID]=uid(); order_number:Mapped[str]=mapped_column(String(32),unique=True,index=True); purchase_request_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("purchase_requests.id"),index=True); vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id"),index=True); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id")); total_amount:Mapped[Decimal]=money(); currency:Mapped[str]=mapped_column(String(3),default="USD"); status:Mapped[str]=mapped_column(String(30),default="issued",index=True); issued_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); issued_at:Mapped[datetime]=now(); closed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class PurchaseOrderItem(Base):
    __tablename__="purchase_order_items"; id:Mapped[uuid.UUID]=uid(); purchase_order_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("purchase_orders.id",ondelete="CASCADE"),index=True); description:Mapped[str]=mapped_column(String(500)); quantity:Mapped[int]=mapped_column(Integer); unit_cost:Mapped[Decimal]=money(); received_quantity:Mapped[int]=mapped_column(Integer,default=0); asset_category_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_categories.id"))
class ReceivingRecord(Base):
    __tablename__="receiving_records"; id:Mapped[uuid.UUID]=uid(); purchase_order_item_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("purchase_order_items.id"),index=True); quantity:Mapped[int]=mapped_column(Integer); condition:Mapped[str]=mapped_column(String(40),default="accepted"); serial_numbers:Mapped[str]=mapped_column(Text,default="[]"); notes:Mapped[str|None]=mapped_column(Text); received_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); received_at:Mapped[datetime]=now()

class ContractType(Base):
    __tablename__="contract_types"; id:Mapped[uuid.UUID]=uid(); name:Mapped[str]=mapped_column(String(100),unique=True); code:Mapped[str]=mapped_column(String(40),unique=True)
class Contract(Base):
    __tablename__="contracts"; id:Mapped[uuid.UUID]=uid(); contract_number:Mapped[str]=mapped_column(String(40),unique=True,index=True); title:Mapped[str]=mapped_column(String(220)); contract_type_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("contract_types.id")); vendor_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id"),index=True); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id")); start_date:Mapped[date]=mapped_column(Date); end_date:Mapped[date]=mapped_column(Date,index=True); value:Mapped[Decimal]=money(); currency:Mapped[str]=mapped_column(String(3),default="USD"); auto_renew:Mapped[bool]=mapped_column(Boolean,default=False); notice_days:Mapped[int]=mapped_column(Integer,default=90); status:Mapped[str]=mapped_column(String(30),default="draft",index=True); terms:Mapped[str|None]=mapped_column(Text); version:Mapped[int]=mapped_column(Integer,default=1); created_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); created_at:Mapped[datetime]=now(); updated_at:Mapped[datetime]=now()
class ContractRenewal(Base):
    __tablename__="contract_renewals"; id:Mapped[uuid.UUID]=uid(); contract_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("contracts.id"),index=True); proposed_end_date:Mapped[date]=mapped_column(Date); proposed_value:Mapped[Decimal]=money(); status:Mapped[str]=mapped_column(String(30),default="review"); approved_by:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); decided_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=now()
class ContractMilestone(Base):
    __tablename__="contract_milestones"; id:Mapped[uuid.UUID]=uid(); contract_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("contracts.id"),index=True); title:Mapped[str]=mapped_column(String(220)); due_date:Mapped[date]=mapped_column(Date,index=True); status:Mapped[str]=mapped_column(String(30),default="pending"); completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class ContractAttachment(Base):
    __tablename__="contract_attachments"; id:Mapped[uuid.UUID]=uid(); contract_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("contracts.id"),index=True); file_name:Mapped[str]=mapped_column(String(255)); storage_key:Mapped[str]=mapped_column(String(500)); sha256:Mapped[str]=mapped_column(String(64)); version:Mapped[int]=mapped_column(Integer); uploaded_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); created_at:Mapped[datetime]=now()

class Warranty(Base):
    __tablename__="asset_warranties"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id"),index=True); vendor_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id")); provider:Mapped[str]=mapped_column(String(220)); coverage:Mapped[str]=mapped_column(Text); start_date:Mapped[date]=mapped_column(Date); end_date:Mapped[date]=mapped_column(Date,index=True); status:Mapped[str]=mapped_column(String(30),default="active")
class WarrantyClaim(Base):
    __tablename__="warranty_claims"; id:Mapped[uuid.UUID]=uid(); warranty_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("asset_warranties.id"),index=True); claim_number:Mapped[str]=mapped_column(String(60),unique=True); description:Mapped[str]=mapped_column(Text); status:Mapped[str]=mapped_column(String(30),default="submitted"); amount:Mapped[Decimal]=money(); submitted_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); submitted_at:Mapped[datetime]=now(); resolved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class SoftwareProduct(Base):
    __tablename__="software_products"; id:Mapped[uuid.UUID]=uid(); name:Mapped[str]=mapped_column(String(220),index=True); publisher:Mapped[str]=mapped_column(String(180)); version:Mapped[str|None]=mapped_column(String(80)); category:Mapped[str|None]=mapped_column(String(100)); __table_args__=(UniqueConstraint("name","publisher","version",name="uq_software_product"),)
class SoftwareLicense(Base):
    __tablename__="software_licenses"; id:Mapped[uuid.UUID]=uid(); license_number:Mapped[str]=mapped_column(String(40),unique=True); product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("software_products.id"),index=True); vendor_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id")); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id")); license_key_ciphertext:Mapped[str|None]=mapped_column(Text); license_type:Mapped[str]=mapped_column(String(40)); seats_purchased:Mapped[int]=mapped_column(Integer); seats_allocated:Mapped[int]=mapped_column(Integer,default=0); purchase_cost:Mapped[Decimal]=money(); renewal_date:Mapped[date|None]=mapped_column(Date,index=True); subscription:Mapped[bool]=mapped_column(Boolean,default=False); status:Mapped[str]=mapped_column(String(30),default="active")
class LicenseAssignment(Base):
    __tablename__="license_assignments"; id:Mapped[uuid.UUID]=uid(); license_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("software_licenses.id"),index=True); asset_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id")); user_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id")); assigned_at:Mapped[datetime]=now(); revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class LicenseUsage(Base):
    __tablename__="license_usage"; id:Mapped[uuid.UUID]=uid(); license_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("software_licenses.id"),index=True); measured_at:Mapped[datetime]=now(); seats_used:Mapped[int]=mapped_column(Integer); source:Mapped[str]=mapped_column(String(80),default="manual")
class LicenseCompliance(Base):
    __tablename__="license_compliance"; id:Mapped[uuid.UUID]=uid(); license_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("software_licenses.id"),index=True); status:Mapped[str]=mapped_column(String(30)); purchased:Mapped[int]=mapped_column(Integer); allocated:Mapped[int]=mapped_column(Integer); variance:Mapped[int]=mapped_column(Integer); findings:Mapped[str]=mapped_column(Text); checked_at:Mapped[datetime]=now()
class InventoryItem(Base):
    __tablename__="inventory_items"; id:Mapped[uuid.UUID]=uid(); sku:Mapped[str]=mapped_column(String(80),unique=True,index=True); name:Mapped[str]=mapped_column(String(220)); item_type:Mapped[str]=mapped_column(String(30)); unit:Mapped[str]=mapped_column(String(30),default="each"); minimum_stock:Mapped[int]=mapped_column(Integer,default=0); reorder_level:Mapped[int]=mapped_column(Integer,default=0); unit_cost:Mapped[Decimal]=money(); vendor_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("vendors.id"))
class InventoryLocation(Base):
    __tablename__="inventory_locations"; id:Mapped[uuid.UUID]=uid(); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id"),index=True); name:Mapped[str]=mapped_column(String(160)); code:Mapped[str]=mapped_column(String(60)); address:Mapped[str|None]=mapped_column(Text); __table_args__=(UniqueConstraint("property_id","code",name="uq_inventory_location_code"),)
class StockBalance(Base):
    __tablename__="stock_balances"; id:Mapped[uuid.UUID]=uid(); item_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("inventory_items.id")); location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("inventory_locations.id")); quantity:Mapped[int]=mapped_column(Integer,default=0); updated_at:Mapped[datetime]=now(); __table_args__=(UniqueConstraint("item_id","location_id",name="uq_stock_balance"),)
class StockMovement(Base):
    __tablename__="stock_movements"; id:Mapped[uuid.UUID]=uid(); item_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("inventory_items.id"),index=True); location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("inventory_locations.id")); movement_type:Mapped[str]=mapped_column(String(30)); quantity:Mapped[int]=mapped_column(Integer); reference_type:Mapped[str|None]=mapped_column(String(40)); reference_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True)); notes:Mapped[str|None]=mapped_column(Text); actor_id:Mapped[str]=mapped_column(String,ForeignKey("users.id")); occurred_at:Mapped[datetime]=now()
class AssetCost(Base):
    __tablename__="asset_costs"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id"),index=True); cost_type:Mapped[str]=mapped_column(String(30)); amount:Mapped[Decimal]=money(); currency:Mapped[str]=mapped_column(String(3),default="USD"); occurred_on:Mapped[date]=mapped_column(Date); description:Mapped[str|None]=mapped_column(Text)
class AssetRelationship(Base):
    __tablename__="asset_relationships"; id:Mapped[uuid.UUID]=uid(); asset_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("enterprise_assets.id"),index=True); target_type:Mapped[str]=mapped_column(String(50)); target_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True); relationship_type:Mapped[str]=mapped_column(String(50),default="related"); notes:Mapped[str|None]=mapped_column(Text); created_by:Mapped[str]=mapped_column(String,ForeignKey("users.id")); created_at:Mapped[datetime]=now(); __table_args__=(UniqueConstraint("asset_id","target_type","target_id","relationship_type",name="uq_asset_relationship"),)
