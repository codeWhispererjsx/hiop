from logging.config import fileConfig
import importlib
import json
import os
import pkgutil
import uuid
from app.models.ticket import Ticket
from sqlalchemy import engine_from_config, inspect, text
from sqlalchemy import pool
from alembic.script import ScriptDirectory

from alembic import context
from app.models.user import User
from app.models.device import Device
from app.models.ticket import Ticket
from app.models.network_scan import NetworkScan
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.system_setting import SystemSetting
from app.models.hierarchy import Property, Building, Floor, Room, Department, NetworkZone
from app.models.discovered_device import DiscoveredDevice, DiscoveryRun
from app.models.inventory_import import ImportedDevice, ImportSession
from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectoryObjectChange,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncError,
    ActiveDirectorySyncRun,
)
from app.models.snmp import (
    SNMPCredential, SNMPTarget, SNMPDeviceProfile, SNMPOIDDefinition,
    SNMPPollingConfiguration, SNMPPollRun, SNMPMetric, SNMPInterface,
    SNMPDiscoveryCandidate,
)
from app.models.topology import (
    Topology, TopologyNode, TopologyLink, TopologyLinkEvidence, NetworkSegment,
    TopologyNodeSegment, DeviceDependency, TopologySnapshot, TopologySnapshotNode,
    TopologySnapshotLink, TopologyChange, TopologyNodePosition, TopologyGroup,
)
from app.models.topology_neighbor import (
    TopologyNeighborCandidate, TopologyNeighborCollectionRun,
    TopologyNeighborObservation,
)
from app.models.topology_inference import (
    TopologyConfidenceHistory, TopologyConflict, TopologyInferenceRun,
    TopologyReviewItem,
)
from app.models.topology_operations import (
    TopologyAlertEvent, TopologyAlertRule, TopologyOperationalRun,
    TopologyScheduleConfiguration,
)
from app.models.analytics import (
    AnalyticsAggregate, AnalyticsAvailability, AnalyticsDataQualityRecord,
    AnalyticsMetricDefinition, AnalyticsRun, CapacityAssessment, CapacityPolicy,
    EntityHealthScore, HealthScoreConfiguration, ReliabilityMeasurement,
    SLADefinition, SLAMeasurement,
)
from app.models.incidents import (
    OperationalIncident, OperationalIncidentSource, OperationalPlaybook,
    OperationalPlaybookVersion, OperationalPlaybookStep, IncidentPlaybookRun,
    IncidentPlaybookStepRun, IncidentParticipant, IncidentTask,
    IncidentChecklistItem, IncidentTimelineEntry, IncidentEvidence,
    IncidentDecision, IncidentCommunicationTemplate, IncidentCommunication,
    IncidentEscalationRule, IncidentEscalation, IncidentResponseTarget,
    IncidentImpactAssessment, IncidentRemediationRecommendation,
    IncidentCauseAssessment, PostIncidentReview, IncidentFollowUpAction,
)
from app.models.automation import (
    AutomationWorkflow, AutomationWorkflowVersion, AutomationAction,
    AutomationWorkflowRun, AutomationWorkflowStep, AutomationStepRun,
)
from app.models.knowledge import *  # noqa: F401,F403 - register Epic 3D metadata
from app.models.change_management import *  # noqa: F401,F403 - register Epic 4 metadata
from app.models.cmdb import *  # noqa: F401,F403 - register Epic 5 metadata
from app.models.problem_management import *  # noqa: F401,F403 - register Epic 6 metadata
from app.models.asset_management import *  # noqa: F401,F403 - register Epic 7 metadata
from app.models.business_intelligence import *  # noqa: F401,F403 - register Epic 8 metadata
from app.models.multi_property import *  # noqa: F401,F403 - register Epic 9 metadata
from app.models.discovery_intelligence import *  # noqa: F401,F403 - register Epic 9.5 metadata
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.segmentation import VLANMembershipObservation
from app.models.asset_intelligence import AssetLifecycleEvent, ManagedAsset
from app.models.procurement import AssetProcurement, ProcurementAssetLink, ProcurementEvent, ProcurementLineItem
from app.models.billing import BillingDocumentReference, BillingEvent, CommercialPlan, OrganizationSubscription
from app.models.local_agent import AgentEnrollment, AgentJob, AgentObservation, LocalAgentRegistration
import app.models as models_package

for model_module in pkgutil.iter_modules(models_package.__path__):
    importlib.import_module(f"app.models.{model_module.name}")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from app.db.database import Base
from app.models.user import User
from app.models.device import Device
target_metadata = Base.metadata
# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def bootstrap_empty_database(connection) -> bool:
    """Create the current schema safely when no application tables exist.

    Historical migrations imported mutable ORM models, so replaying them on a
    brand-new database is not deterministic. Existing databases still follow
    the normal migration path; this baseline is used only for a truly empty DB.
    """
    if inspect(connection).get_table_names():
        return False

    target_metadata.create_all(connection)
    if connection.dialect.name == "postgresql":
        for sequence in (
            "managed_asset_number_seq",
            "asset_procurement_number_seq",
            "operational_vendor_number_seq",
            "local_agent_number_seq",
            "problem_number_seq",
            "v4g_change_number_seq",
            "v4h_article_number_seq",
        ):
            connection.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {sequence} START 1"))

    if "commercial_plans" in target_metadata.tables:
        plans = (
            ("starter", "Starter", "Smaller properties", ["discovery", "monitoring", "alerts", "assets", "reporting_basic"], {"devices": 250, "assets": 250, "properties": 1, "users": 10, "agents": 1}, 10),
            ("core", "Core", "Growing hotel IT teams", ["discovery", "monitoring", "alerts", "assets", "reporting_basic", "topology", "network_context", "service_management", "problem_management", "change_management", "procurement", "vendors", "knowledge", "multi_property", "reporting_advanced"], {"devices": 1000, "assets": 1000, "properties": 3, "users": 50, "agents": 3}, 20),
            ("enterprise", "Enterprise", "Hotel groups and larger environments", ["discovery", "monitoring", "alerts", "assets", "reporting_basic", "topology", "network_context", "service_management", "problem_management", "change_management", "procurement", "vendors", "knowledge", "multi_property", "reporting_advanced", "enterprise_support"], {}, 30),
        )
        plan_table = target_metadata.tables["commercial_plans"]
        connection.execute(plan_table.insert(), [
            {
                "id": uuid.uuid4(), "code": code, "name": name,
                "description": audience, "audience": audience, "currency": "NGN",
                "trial_days": 14, "features": "[]", "entitlements": json.dumps(entitlements),
                "limits": json.dumps(limits), "is_active": True, "sort_order": order,
            }
            for code, name, audience, entitlements, limits, order in plans
        ])

    head = ScriptDirectory.from_config(config).get_current_head()
    connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
    connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:head)"), {"head": head})
    return True



def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.begin() as connection:
        if bootstrap_empty_database(connection):
            return
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
