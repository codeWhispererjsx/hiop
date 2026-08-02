"""Multi-property operations and corporate management.

Revision ID: 1c2d3e4f5a69
Revises: 0b1c2d3e4f58
"""
from alembic import op
from app.models.multi_property import *

revision="1c2d3e4f5a69";down_revision="0b1c2d3e4f58";branch_labels=None;depends_on=None
TABLES=[BusinessUnit,Region,Country,PropertyGroup,PropertyCluster,PropertyHierarchyMembership,CorporateOffice,RegionalOffice,AdministrativeScope,CorporateAdministrator,RegionalAdministrator,PropertyAdministrator,DelegatedAdministrator,GlobalSetting,RegionalSetting,PropertySetting,InheritedSetting,ConfigurationPolicy,Policy,PolicyVersion,PolicyAssignment,PolicyCompliance,PolicyException,GlobalNotification,ExecutiveOperationsCache]
def upgrade():
    bind=op.get_bind()
    for model in TABLES:model.__table__.create(bind,checkfirst=True)
def downgrade():
    bind=op.get_bind()
    for model in reversed(TABLES):model.__table__.drop(bind,checkfirst=True)
