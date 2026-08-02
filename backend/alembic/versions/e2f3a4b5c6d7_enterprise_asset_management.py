"""Enterprise Asset, Vendor, Procurement and Contract Lifecycle.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""
from alembic import op
from app.models.asset_management import *

revision="e2f3a4b5c6d7"; down_revision="d1e2f3a4b5c6"; branch_labels=None; depends_on=None
TABLES=[AssetCategory,AssetSubcategory,AssetStatus,AssetOwnership,EnterpriseAsset,AssetLifecycle,AssetLocationHistory,AssetAssignment,AssetTransfer,AssetDisposal,VendorCategory,Vendor,VendorContact,VendorLocation,VendorPerformance,VendorReview,VendorCertification,ProcurementBudget,PurchaseRequest,ProcurementApproval,PurchaseOrder,PurchaseOrderItem,ReceivingRecord,ContractType,Contract,ContractRenewal,ContractMilestone,ContractAttachment,Warranty,WarrantyClaim,SoftwareProduct,SoftwareLicense,LicenseAssignment,LicenseUsage,LicenseCompliance,InventoryItem,InventoryLocation,StockBalance,StockMovement,AssetCost,AssetRelationship]
def upgrade():
    bind=op.get_bind()
    for model in TABLES:model.__table__.create(bind,checkfirst=True)
def downgrade():
    bind=op.get_bind()
    for model in reversed(TABLES):model.__table__.drop(bind,checkfirst=True)
