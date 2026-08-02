from logging.config import fileConfig
from app.models.ticket import Ticket
from sqlalchemy import engine_from_config
from sqlalchemy import pool

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
from app.models.hospitality_operations import HospitalityTechnologyService

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

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

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
