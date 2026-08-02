"""Enterprise discovery and configuration intelligence.

Revision ID: 2c3d4e5f6a70
Revises: 1c2d3e4f5a69
"""
from alembic import op
from app.models.discovery_intelligence import *

revision="2c3d4e5f6a70";down_revision="1c2d3e4f5a69";branch_labels=None;depends_on=None
TABLES=[DiscoveryPolicy,DiscoveryCredential,DiscoveryJob,DiscoveryStage,DiscoveryTask,DiscoveryResult,DiscoveryEvidence,DiscoveryFingerprint,DiscoveryOUI,DiscoveryChangeSuggestion]
OUI=[("00000C","Cisco"),("001B21","Intel"),("001C23","Dell"),("3C52A1","Hewlett Packard Enterprise"),("9C8C6E","HPE Aruba"),("0019E2","Juniper"),("00090F","Fortinet"),("4C5E0C","MikroTik"),("F09FC2","Ubiquiti"),("E8F2E2","Lenovo"),("001CB3","Apple"),("001599","Samsung"),("001E8F","Canon"),("001B67","Epson"),("001BA9","Brother"),("44A6E5","Hikvision"),("00408C","Axis"),("001565","Yealink"),("000B82","Grandstream"),("00155D","Microsoft"),("000C29","VMware")]
def upgrade():
    bind=op.get_bind()
    for model in TABLES:model.__table__.create(bind,checkfirst=True)
    table=DiscoveryOUI.__table__
    op.bulk_insert(table,[{"prefix":p,"vendor":v,"source":"bundled","version":"2026.1"} for p,v in OUI])
def downgrade():
    bind=op.get_bind()
    for model in reversed(TABLES):model.__table__.drop(bind,checkfirst=True)
