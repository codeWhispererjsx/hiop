"""enterprise configuration management database

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""
from alembic import op

revision="c0d1e2f3a4b5";down_revision="b9c0d1e2f3a4";branch_labels=None;depends_on=None

TABLES=("ci_classes","ci_types","ci_statuses","ci_lifecycles","configuration_items","ci_attributes","ci_attribute_history","ci_identifiers","ci_aliases","ci_relationship_types","ci_relationships","ci_relationship_history","ci_lifecycle_history","ci_dependency_graphs","ci_reconciliation_candidates","ci_health_snapshots")
CLASSES=(("Infrastructure","infrastructure"),("Network","network"),("Hospitality","hospitality"),("Cloud","cloud"),("Applications","applications"),("Facilities","facilities"))
TYPES={
"infrastructure":["Server","Virtual Machine","Hypervisor","Cluster","Storage","SAN","NAS"],
"network":["Router","Switch","Firewall","Wireless Controller","Access Point","VPN Gateway","Load Balancer"],
"hospitality":["Opera PMS","POS","IPTV","Door Lock Controller","CCTV Platform","PBX","Guest WiFi","Booking Integration"],
"cloud":["Azure Resource","AWS Resource","SaaS Service","API Gateway"],
"applications":["Web Application","Database","API","Background Worker","Service"],
"facilities":["Rack","UPS","Generator","MDF","IDF","Patch Panel","Building","Floor","Room"],
}
RELATIONSHIPS=(("Runs On","runs_on","Hosts","many_to_one"),("Hosts","hosts","Runs On","one_to_many"),("Depends On","depends_on","Supports","many_to_many"),("Connected To","connected_to","Connected To","many_to_many"),("Backs Up","backs_up","Backed Up By","many_to_many"),("Uses","uses","Used By","many_to_many"),("Managed By","managed_by","Manages","many_to_one"),("Contained In","contained_in","Contains","many_to_one"),("Located In","located_in","Contains","many_to_one"),("Replicates To","replicates_to","Replicated From","many_to_many"),("Redundant With","redundant_with","Redundant With","many_to_many"),("Monitored By","monitored_by","Monitors","many_to_many"),("Supports","supports","Depends On","one_to_many"),("Owned By","owned_by","Owns","many_to_one"))

def code(value):return value.lower().replace(" ","_").replace("/","_")
def upgrade():
    from app.models import cmdb  # noqa:F401
    from app.models import device,discovered_device,hierarchy  # noqa:F401
    from app.db.database import Base
    bind=op.get_bind()
    for name in TABLES:Base.metadata.tables[name].create(bind,checkfirst=True)
    class_table=Base.metadata.tables["ci_classes"];type_table=Base.metadata.tables["ci_types"]
    ids={}
    for name,class_code in CLASSES:
        result=bind.execute(class_table.insert().values(name=name,code=class_code,domain=class_code,description=f"{name} configuration items",enabled=True));ids[class_code]=result.inserted_primary_key[0]
    for class_code,names in TYPES.items():
        for name in names:bind.execute(type_table.insert().values(class_id=ids[class_code],name=name,code=code(name),category=class_code,attribute_schema="{}",enabled=True))
    status=Base.metadata.tables["ci_statuses"]
    for name,status_code,operational,terminal in (("Active","active",True,False),("Inactive","inactive",False,False),("Maintenance","maintenance",False,False),("Retired","retired",False,True),("Archived","archived",False,True)):bind.execute(status.insert().values(name=name,code=status_code,operational=operational,terminal=terminal))
    lifecycle=Base.metadata.tables["ci_lifecycles"]
    for order,name in enumerate(("Planned","Ordered","Installed","Operational","Maintenance","Retired","Archived")):bind.execute(lifecycle.insert().values(name=name,code=name.lower(),sequence_order=order,terminal=name=="Archived"))
    rel=Base.metadata.tables["ci_relationship_types"]
    for name,rel_code,inverse,cardinality in RELATIONSHIPS:bind.execute(rel.insert().values(name=name,code=rel_code,inverse_name=inverse,cardinality=cardinality,directional=name not in {"Connected To","Redundant With"},enabled=True))

def downgrade():
    for name in reversed(TABLES):op.drop_table(name)
