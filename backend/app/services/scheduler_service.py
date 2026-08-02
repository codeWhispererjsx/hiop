import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.core.config import settings
from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncRun,
)
from app.services.network_service import scan_all_devices
from app.models.snmp import SNMPCredential, SNMPPollingConfiguration, SNMPPollRun, SNMPTarget
from app.models.topology import Topology, TopologyNode
from app.models.topology_inference import TopologyInferenceRun
from app.models.topology_operations import TopologyOperationalRun, TopologyScheduleConfiguration
from app.models.analytics import AnalyticsRun, AnalyticsScheduleConfiguration
from app.models.automation import AutomationApprovalRequest, AutomationWorkflow, AutomationWorkflowRun, AutomationWorkflowVersion
from app.models.automation_triggers import AutomationEventRecord,AutomationTriggerExecution,AutomationTriggerSubscription,AutomationWorkflowSchedule
from app.models.incidents import IncidentFollowUpAction,IncidentPlaybookRun,IncidentTask,OperationalIncident,PostIncidentReview
from app.models.knowledge import Document, KnowledgeArticle, KnowledgeRelationship, StandardProcedure
from app.models.change_management import ChangeApproval, ChangeRequest, MaintenanceWindow, Release, RiskAssessment
from app.models.cmdb import CIHealthSnapshot, CIReconciliationCandidate, CIRelationship, ConfigurationItem
from app.models.problem_management import ActionTask, KnownError, Problem, ProblemCorrelationSuggestion
from app.models.asset_management import Contract, EnterpriseAsset, InventoryItem, SoftwareLicense, StockBalance, Vendor, VendorPerformance, Warranty
from app.models.business_intelligence import DashboardCache, ExecutiveDashboard, KPI, KPIDefinition, KPISnapshot, KPIValue, ReportExecution, ReportRecipient, ScheduledReport
from app.models.hierarchy import Property
from app.models.multi_property import ExecutiveOperationsCache, GlobalNotification, GlobalSetting, InheritedSetting, PolicyAssignment, PolicyCompliance, PropertyHierarchyMembership, PropertySetting, RegionalSetting
from app.services.multi_property_service import property_ids_for_scope
from app.models.discovery_intelligence import DiscoveryEvidence,DiscoveryJob,DiscoveryOUI,DiscoveryPolicy,DiscoveryResult
from app.services.discovery_intelligence_service import DiscoveryIntelligenceService,confidence,parse_json,review_status


scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)
AD_JOB_PREFIX = "active_directory_sync_"
SNMP_JOB_PREFIX = "snmp_poll_"
SNMP_CLEANUP_JOB_ID = "snmp_retention_cleanup"
TOPOLOGY_JOB_PREFIX = "topology_"
TOPOLOGY_CLEANUP_JOB_ID = "topology_retention_cleanup"
TOPOLOGY_JOB_TYPES = ("collection", "inference", "snapshot", "changes", "health")
ANALYTICS_JOB_PREFIX = "analytics_"
AUTOMATION_JOB_PREFIX = "automation_workflow_"
AUTOMATION_DELAY_JOB_PREFIX = "automation_delayed_"
AUTOMATION_OUTBOX_JOB_ID = "automation_event_outbox"
AUTOMATION_RETENTION_JOB_ID = "automation_retention_cleanup"
INCIDENT_JOB_PREFIX = "incident_"
INCIDENT_JOB_INTERVALS = {
    "sla_evaluation": 5,
    "overdue_tasks": 5,
    "escalations": 5,
    "communication_reminders": 15,
    "monitoring_completion": 15,
    "post_incident_reminders": 60,
    "follow_up_reminders": 60,
    "retention_cleanup": 1440,
}
KNOWLEDGE_JOB_PREFIX = "knowledge_"
KNOWLEDGE_JOB_INTERVALS = {
    "scheduled_lifecycle": 5,
    "review_reminders": 1440,
    "expired_documents": 1440,
    "broken_links": 1440,
    "revision_reminders": 1440,
    "statistics": 60,
    "search_index": 1440,
}
CHANGE_JOB_PREFIX = "change_management_"
CHANGE_JOB_INTERVALS = {
    "approval_reminders": 60, "upcoming_maintenance": 60,
    "missed_approvals": 60, "expired_rfc_cleanup": 1440,
    "conflict_detection": 60, "release_reminders": 1440,
    "risk_recalculation": 1440, "calendar_synchronization": 60,
}
CMDB_JOB_PREFIX = "cmdb_"
CMDB_JOB_INTERVALS = {
    "ci_verification": 1440, "relationship_validation": 1440,
    "health_recalculation": 360, "duplicate_detection": 1440,
    "orphan_detection": 1440, "discovery_reconciliation": 360,
    "expired_warranty_notifications": 1440,
}
PROBLEM_JOB_INTERVALS={"review_reminders":1440,"capa_due_reminders":60,"known_error_review_reminders":1440,"recurring_incident_detection":60,"problem_aging_alerts":1440,"dashboard_statistics":60}
ASSET_JOB_INTERVALS={"warranty_reminders":1440,"contract_renewal_reminders":1440,"license_renewal_reminders":1440,"inventory_threshold_alerts":60,"asset_lifecycle_reviews":1440,"depreciation_recalculation":1440,"vendor_score_aggregation":1440}
BI_JOB_INTERVALS={"kpi_recalculation":60,"snapshot_generation":1440,"report_scheduling":15,"email_distribution":15,"trend_aggregation":60,"capacity_recalculation":360,"dashboard_cache_refresh":15}
MULTI_PROPERTY_JOB_INTERVALS={"organization_synchronization":1440,"policy_compliance_checks":360,"cross_property_kpi_aggregation":60,"dashboard_cache_refresh":15,"notification_routing":5,"executive_report_generation":43200}
DISCOVERY_INTELLIGENCE_JOB_INTERVALS={"incremental_discovery":60,"full_discovery":10080,"vendor_database_updates":10080,"confidence_recalculation":360,"device_aging":1440,"stale_device_detection":360}
ANALYTICS_JOB_TYPES = ("aggregate", "availability", "health_score", "capacity", "SLA", "reliability", "data_quality", "baseline", "anomaly", "correlation", "insight", "anomaly_recovery", "retention_cleanup")
SNMP_GROUPS = {
    "availability": ("availability_poll_enabled", "availability_interval_seconds", "availability"),
    "system": ("system_poll_enabled", "system_interval_seconds", "system"),
    "interface_inventory": ("inventory_poll_enabled", "interface_inventory_interval_seconds", "interfaces_preview"),
    "interface_performance": ("performance_poll_enabled", "interface_performance_interval_seconds", "custom_profile"),
    "device_performance": ("performance_poll_enabled", "device_performance_interval_seconds", "custom_profile"),
}

def automation_job_id(schedule_id: str) -> str:
    return f"{AUTOMATION_JOB_PREFIX}{schedule_id}"

def remove_automation_job(schedule_id: str) -> bool:
    job=scheduler.get_job(automation_job_id(schedule_id))
    if job:scheduler.remove_job(job.id);return True
    return False

def scheduled_automation_workflow(schedule_id: str) -> None:
    db=SessionLocal()
    try:
        schedule=db.get(AutomationWorkflowSchedule,schedule_id)
        if not schedule or not schedule.enabled:return
        now=datetime.now(timezone.utc)
        if schedule.maximum_runs is not None and schedule.runs_completed>=schedule.maximum_runs:
            schedule.enabled=False;db.commit();remove_automation_job(schedule_id);return
        if schedule.end_at and now>schedule.end_at:
            schedule.enabled=False;schedule.last_run_at=now;schedule.last_run_status="expired";db.commit();remove_automation_job(schedule_id);return
        if schedule.start_at and now<schedule.start_at:return
        if schedule.blackout_behavior=="suppress" and schedule.blackout_start and schedule.blackout_end and schedule.blackout_start<=now<=schedule.blackout_end:
            schedule.last_run_at=now;schedule.last_run_status="suppressed_blackout";db.commit();return
        if schedule.maintenance_behavior=="suppress":
            from app.services.automation_trigger_service import _maintenance_active
            if _maintenance_active(db,schedule.property_id):schedule.last_run_at=now;schedule.last_run_status="suppressed_maintenance";db.commit();return
        workflow=db.get(AutomationWorkflow,schedule.workflow_id);version=db.get(AutomationWorkflowVersion,schedule.workflow_version_id)
        if not workflow or not workflow.enabled or not version or version.status!="approved":
            schedule.last_run_at=now;schedule.last_run_status="invalid_configuration";db.commit();return
        active=db.query(AutomationWorkflowRun).filter(AutomationWorkflowRun.workflow_id==workflow.id,AutomationWorkflowRun.status.in_(("pending","running","waiting_approval"))).first()
        if active:schedule.last_run_at=now;schedule.last_run_status="overlap_blocked";db.commit();return
        if schedule.approval_mode=="always_require":
            created_run=AutomationWorkflowRun(property_id=schedule.property_id,workflow_id=workflow.id,workflow_version_id=version.id,status="waiting_approval",trigger_type="scheduled",triggered_by="scheduler",idempotency_key=f"schedule:{schedule.id}:{now.isoformat()}");db.add(created_run);db.flush();db.add(AutomationApprovalRequest(workflow_run_id=created_run.id,requested_by="scheduler"));result={"status":"waiting_approval"}
        else:
            from app.api.v1.automation import RunWrite,run_workflow
            result=run_workflow(workflow.id,RunWrite(idempotency_key=f"schedule:{schedule.id}:{now.isoformat()}",dry_run=False),db,SimpleNamespace(id=None,username="scheduler",role="admin"))
            created_run=db.get(AutomationWorkflowRun,result["run_id"]);created_run.trigger_type="scheduled"
        schedule.runs_completed+=1;schedule.last_run_at=now;schedule.last_run_status=result["status"];db.commit()
        if schedule.schedule_type=="one_time":schedule.enabled=False;db.commit();remove_automation_job(schedule_id)
    except Exception:
        db.rollback();logger.exception("Scheduled automation workflow failed schedule_id=%s",schedule_id)
    finally:db.close()

def delayed_automation_event(workflow_id: str, event_id: str, subscription_id: str, execution_id: str) -> None:
    db=SessionLocal()
    try:
        workflow=db.get(AutomationWorkflow,workflow_id);subscription=db.get(AutomationTriggerSubscription,subscription_id);execution=db.get(AutomationTriggerExecution,execution_id);event=db.query(AutomationEventRecord).filter_by(event_id=event_id).first()
        if not workflow or not subscription or not execution or not event or not workflow.enabled or not subscription.enabled:
            if execution:execution.status="suppressed";execution.suppression_reason="delayed_trigger_invalid";db.commit()
            return
        now=datetime.now(timezone.utc)
        if subscription.blackout_behavior=="suppress" and subscription.blackout_start and subscription.blackout_end and subscription.blackout_start<=now<=subscription.blackout_end:
            execution.status="suppressed";execution.suppression_reason="blackout_window";db.commit();return
        if subscription.maintenance_behavior=="suppress":
            from app.services.automation_trigger_service import _maintenance_active
            if _maintenance_active(db,subscription.property_id):execution.status="suppressed";execution.suppression_reason="maintenance_window";db.commit();return
        from app.api.v1.automation import RunWrite,run_workflow
        result=run_workflow(workflow.id,RunWrite(idempotency_key=f"event:{event_id}:{subscription_id}",dry_run=False),db,SimpleNamespace(id=None,username="automation:delayed",role="admin"))
        run=db.get(AutomationWorkflowRun,result["run_id"]);run.trigger_type="internal_event";execution.status="triggered";db.commit()
    except Exception:
        db.rollback()
        try:
            execution=db.get(AutomationTriggerExecution,execution_id)
            if execution:execution.status="failed";execution.suppression_reason="delayed_execution_failed";db.commit()
        except Exception:db.rollback()
        logger.exception("Delayed automation event failed execution_id=%s",execution_id)
    finally:db.close()

def reconcile_automation_jobs(db) -> dict[str,int]:
    if not settings.scheduler_enabled:return {"registered":0,"removed":0}
    if not scheduler.running:scheduler.start()
    registered=removed=0;expected=set()
    for row in db.query(AutomationWorkflowSchedule).all():
        job_id=automation_job_id(str(row.id))
        workflow=db.get(AutomationWorkflow,row.workflow_id);version=db.get(AutomationWorkflowVersion,row.workflow_version_id)
        valid=row.enabled and workflow and workflow.enabled and version and version.status=="approved"
        if not valid:
            if scheduler.get_job(job_id):scheduler.remove_job(job_id);removed+=1
            continue
        expected.add(job_id)
        common={"id":job_id,"replace_existing":True,"max_instances":1,"coalesce":True,"misfire_grace_time":300}
        if row.schedule_type=="interval" and row.interval_minutes:
            scheduler.add_job(scheduled_automation_workflow,"interval",minutes=row.interval_minutes,start_date=row.start_at,end_date=row.end_at,jitter=row.jitter_seconds or None,args=[str(row.id)],**common);registered+=1
        elif row.schedule_type=="one_time" and row.next_run_at and row.next_run_at>datetime.now(timezone.utc):
            scheduler.add_job(scheduled_automation_workflow,"date",run_date=row.next_run_at,args=[str(row.id)],**common);registered+=1
        elif row.schedule_type in {"daily","weekly","monthly"} and row.preferred_time:
            hour,minute=(int(part) for part in row.preferred_time.split(":"));cron={"hour":hour,"minute":minute,"timezone":row.timezone,"start_date":row.start_at,"end_date":row.end_at,"jitter":row.jitter_seconds or None}
            if row.schedule_type=="weekly":cron["day_of_week"]=row.day_of_week
            if row.schedule_type=="monthly":cron["day"]=row.day_of_month
            scheduler.add_job(scheduled_automation_workflow,"cron",args=[str(row.id)],**cron,**common);registered+=1
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(AUTOMATION_JOB_PREFIX) and job.id not in expected:scheduler.remove_job(job.id);removed+=1
    return {"registered":registered,"removed":removed}

def recover_stale_automation_runs(db,timeout_minutes: int=30) -> int:
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=timeout_minutes);rows=db.query(AutomationWorkflowRun).filter(AutomationWorkflowRun.trigger_type.in_(("scheduled","internal_event","retry")),AutomationWorkflowRun.status.in_(("pending","running")),AutomationWorkflowRun.created_at<cutoff).all()
    for row in rows:row.status="failed";row.error_summary="Recovered stale automation run after scheduler startup."
    if rows:db.commit()
    return len(rows)

def scheduled_automation_outbox():
    db=SessionLocal()
    try:
        from app.services.automation_event_outbox_service import process_outbox_batch
        process_outbox_batch(db,100)
    except Exception:db.rollback();logger.exception("Automation outbox processing failed")
    finally:db.close()

def scheduled_automation_retention():
    db=SessionLocal()
    try:
        from app.services.automation_event_outbox_service import cleanup_retention
        cleanup_retention(db,30,500)
    except Exception:db.rollback();logger.exception("Automation retention cleanup failed")
    finally:db.close()


def incident_job_id(job_type: str) -> str:
    if job_type not in INCIDENT_JOB_INTERVALS:
        raise ValueError("Unsupported incident scheduler job")
    return f"{INCIDENT_JOB_PREFIX}{job_type}"


def recover_stale_incident_runs(db, timeout_minutes: int = 240) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    rows = db.query(IncidentPlaybookRun).filter(
        IncidentPlaybookRun.status.in_(("validating", "ready", "running")),
        IncidentPlaybookRun.updated_at < cutoff,
    ).all()
    for row in rows:
        row.status = "timed_out"
        row.completed_at = datetime.now(timezone.utc)
        row.error_category = "stale_run"
        row.error_summary = "Recovered stale incident playbook run after scheduler startup."
    if rows:
        db.commit()
    return len(rows)


def scheduled_incident_evaluation(job_type: str) -> None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        active = db.query(OperationalIncident).filter(
            OperationalIncident.status.notin_(("closed", "cancelled", "duplicate", "merged"))
        ).limit(1000).all()
        if job_type in {"sla_evaluation", "escalations", "communication_reminders"}:
            from app.services.incident_escalation_service import evaluate_incident
            for incident in active:
                evaluate_incident(db, incident, now)
        if job_type == "overdue_tasks":
            from app.services.incident_orchestration_service import process_playbook_timeouts
            process_playbook_timeouts(db, now)
            tasks = db.query(IncidentTask).filter(
                IncidentTask.due_at < now,
                IncidentTask.status.notin_(("completed", "verified", "cancelled", "overdue")),
            ).limit(1000).all()
            for task in tasks:
                task.status = "overdue"
        if job_type == "post_incident_reminders":
            db.query(PostIncidentReview).filter(
                PostIncidentReview.status.in_(("required", "scheduled")),
                PostIncidentReview.scheduled_at.isnot(None),
                PostIncidentReview.scheduled_at < now,
            ).limit(1000).all()
        if job_type == "follow_up_reminders":
            actions = db.query(IncidentFollowUpAction).filter(
                IncidentFollowUpAction.due_at < now,
                IncidentFollowUpAction.status.notin_(("completed", "verified", "cancelled")),
            ).limit(1000).all()
            for action in actions:
                action.status = "overdue"
        # Retention is deliberately conservative: authoritative incident history,
        # evidence, audit, and post-incident records are never automatically removed.
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Incident scheduler job failed job_type=%s", job_type)
    finally:
        db.close()


def reconcile_incident_jobs() -> dict[str, int]:
    if not settings.scheduler_enabled:
        return {"registered": 0, "removed": 0}
    if not scheduler.running:
        scheduler.start()
    expected = set()
    for job_type, minutes in INCIDENT_JOB_INTERVALS.items():
        job_id = incident_job_id(job_type)
        expected.add(job_id)
        scheduler.add_job(
            scheduled_incident_evaluation, "interval", minutes=minutes,
            id=job_id, args=[job_type], replace_existing=True, max_instances=1,
            coalesce=True, misfire_grace_time=min(minutes * 60, 600),
        )
    removed = 0
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(INCIDENT_JOB_PREFIX) and job.id not in expected:
            scheduler.remove_job(job.id)
            removed += 1
    return {"registered": len(expected), "removed": removed}


def remove_incident_jobs() -> int:
    jobs = [job for job in scheduler.get_jobs() if job.id.startswith(INCIDENT_JOB_PREFIX)]
    for job in jobs:
        scheduler.remove_job(job.id)
    return len(jobs)


def knowledge_job_id(job_type: str) -> str:
    if job_type not in KNOWLEDGE_JOB_INTERVALS:
        raise ValueError("Unsupported knowledge scheduler job")
    return f"{KNOWLEDGE_JOB_PREFIX}{job_type}"


def scheduled_knowledge_job(job_type: str) -> None:
    db = SessionLocal()
    now_value = datetime.now(timezone.utc)
    try:
        if job_type == "scheduled_lifecycle":
            from app.services.knowledge_service import publish_and_archive_due
            publish_and_archive_due(db, now_value)
        elif job_type == "expired_documents":
            expired = 0
            for row in db.query(Document).filter(Document.expires_at <= now_value, Document.status.notin_(("expired", "archived"))).limit(1000):
                row.status = "expired"; expired += 1
            if expired:
                from app.services.knowledge_notification_service import notify_knowledge
                notify_knowledge(db, "HIOP knowledge documents expired", f"{expired} document records entered the expired review queue.")
        elif job_type in {"review_reminders", "revision_reminders"}:
            articles = db.query(KnowledgeArticle).filter(KnowledgeArticle.next_review_at <= now_value).limit(1000).count()
            procedures = db.query(StandardProcedure).filter(StandardProcedure.next_review_at <= now_value).limit(1000).count()
            if articles or procedures:
                from app.services.knowledge_notification_service import notify_knowledge
                notify_knowledge(db, "HIOP knowledge review reminder", f"Review queue: {articles} articles and {procedures} procedures are due.")
        elif job_type == "broken_links":
            # Validate knowledge-owned targets without deleting historical links.
            # External operational entities remain "unchecked" because their
            # lifecycle and access rules belong to their source modules.
            from app.models.knowledge import (
                CatalogItem, Document, KnowledgeArticle, Runbook,
                StandardProcedure, TroubleshootingGuide,
            )
            targets = {
                "article": KnowledgeArticle, "runbook": Runbook,
                "sop": StandardProcedure, "service": CatalogItem,
                "document": Document, "troubleshooting": TroubleshootingGuide,
            }
            for row in db.query(KnowledgeRelationship).limit(5000):
                statuses = []
                for entity_type, entity_id in ((row.source_type, row.source_id), (row.target_type, row.target_id)):
                    model = targets.get(entity_type)
                    statuses.append("unchecked" if model is None else ("valid" if db.get(model, entity_id) else "broken"))
                row.validation_status = "broken" if "broken" in statuses else ("valid" if all(value == "valid" for value in statuses) else "unchecked")
                row.last_validated_at = now_value
        elif job_type == "statistics":
            db.query(KnowledgeArticle.id, KnowledgeArticle.view_count).limit(5000).all()
        elif job_type == "search_index" and db.bind.dialect.name == "postgresql":
            from sqlalchemy import text
            db.execute(text("ANALYZE knowledge_articles"))
            db.execute(text("ANALYZE documents"))
            db.execute(text("ANALYZE troubleshooting_guides"))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Knowledge scheduler job failed job_type=%s", job_type)
    finally:
        db.close()


def reconcile_knowledge_jobs() -> dict[str, int]:
    if not settings.scheduler_enabled:
        return {"registered": 0, "removed": 0}
    if not scheduler.running:
        scheduler.start()
    expected = set()
    for job_type, minutes in KNOWLEDGE_JOB_INTERVALS.items():
        job_id = knowledge_job_id(job_type); expected.add(job_id)
        scheduler.add_job(
            scheduled_knowledge_job, "interval", minutes=minutes, id=job_id,
            args=[job_type], replace_existing=True, max_instances=1,
            coalesce=True, misfire_grace_time=min(minutes * 60, 3600),
        )
    removed = 0
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(KNOWLEDGE_JOB_PREFIX) and job.id not in expected:
            scheduler.remove_job(job.id); removed += 1
    return {"registered": len(expected), "removed": removed}


def change_job_id(job_type: str) -> str:
    if job_type not in CHANGE_JOB_INTERVALS: raise ValueError("Unsupported change-management scheduler job")
    return f"{CHANGE_JOB_PREFIX}{job_type}"


def scheduled_change_job(job_type: str) -> None:
    db = SessionLocal(); now = datetime.now(timezone.utc)
    try:
        notice = None
        if job_type in {"approval_reminders", "missed_approvals"}:
            query = db.query(ChangeApproval).filter_by(status="pending")
            if job_type == "missed_approvals": query = query.filter(ChangeApproval.due_at < now)
            count = query.limit(1000).count()
            if count: notice = ("HIOP change approval reminder", f"{count} change approvals require review.")
        elif job_type == "upcoming_maintenance":
            count = db.query(MaintenanceWindow).filter(MaintenanceWindow.status == "approved", MaintenanceWindow.start_at >= now, MaintenanceWindow.start_at <= now + timedelta(hours=24)).limit(1000).count()
            if count: notice = ("Upcoming HIOP maintenance", f"{count} approved maintenance windows begin within 24 hours.")
        elif job_type == "expired_rfc_cleanup":
            cutoff = now - timedelta(days=365)
            for row in db.query(ChangeRequest).filter(ChangeRequest.status == "draft", ChangeRequest.updated_at < cutoff).limit(500): row.status = "cancelled"; row.updated_at = now
        elif job_type == "conflict_detection":
            from app.services.change_management_service import detect_window_conflicts
            for window in db.query(MaintenanceWindow).filter(MaintenanceWindow.status.in_(("draft", "approved")), MaintenanceWindow.end_at >= now).limit(1000): detect_window_conflicts(db, window)
        elif job_type == "release_reminders":
            count = db.query(Release).filter(Release.status.in_(("approved", "scheduled")), Release.planned_start >= now, Release.planned_start <= now + timedelta(days=7)).limit(1000).count()
            if count: notice = ("Upcoming HIOP releases", f"{count} releases are planned within seven days.")
        elif job_type == "risk_recalculation":
            for change in db.query(ChangeRequest).filter(~ChangeRequest.status.in_(("closed", "cancelled"))).limit(1000):
                latest = db.query(RiskAssessment).filter_by(change_request_id=change.id).order_by(RiskAssessment.version.desc()).first()
                if latest: change.risk_level = latest.risk_level
        elif job_type == "calendar_synchronization":
            # Internal calendar state is authoritative; external calendar adapters
            # remain explicit deployment integrations.
            db.query(MaintenanceWindow.id).filter(MaintenanceWindow.end_at >= now).limit(5000).all()
        if notice:
            from app.services.change_notification_service import notify_change
            notify_change(db, *notice)
        db.commit()
    except Exception:
        db.rollback(); logger.exception("Change-management scheduler job failed job_type=%s", job_type)
    finally: db.close()


def reconcile_change_jobs() -> dict[str, int]:
    if not settings.scheduler_enabled: return {"registered": 0, "removed": 0}
    if not scheduler.running: scheduler.start()
    expected = set()
    for job_type, minutes in CHANGE_JOB_INTERVALS.items():
        job_id = change_job_id(job_type); expected.add(job_id)
        scheduler.add_job(scheduled_change_job, "interval", minutes=minutes, id=job_id, args=[job_type], replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=min(minutes * 60, 3600))
    removed = 0
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(CHANGE_JOB_PREFIX) and job.id not in expected: scheduler.remove_job(job.id); removed += 1
    return {"registered": len(expected), "removed": removed}


def cmdb_job_id(job_type: str) -> str:
    if job_type not in CMDB_JOB_INTERVALS: raise ValueError("Unsupported CMDB scheduler job")
    return f"{CMDB_JOB_PREFIX}{job_type}"


def scheduled_cmdb_job(job_type: str) -> None:
    db=SessionLocal();now=datetime.now(timezone.utc)
    try:
        from app.services.cmdb_service import calculate_health,graph_for,reconciliation_candidates
        if job_type=="ci_verification":
            db.query(ConfigurationItem).filter(ConfigurationItem.last_verified_at.is_not(None),ConfigurationItem.last_verified_at<now-timedelta(days=30),ConfigurationItem.verification_status=="verified").update({ConfigurationItem.verification_status:"stale"},synchronize_session=False)
        elif job_type=="relationship_validation":graph_for(db,max_depth=12,max_nodes=2000)
        elif job_type in {"health_recalculation","orphan_detection"}:
            calculate_health(db,None)
            property_ids=[row[0] for row in db.query(ConfigurationItem.property_id).filter(ConfigurationItem.property_id.is_not(None)).distinct().limit(1000)]
            for property_id in property_ids:calculate_health(db,property_id)
        elif job_type in {"duplicate_detection","discovery_reconciliation"}:reconciliation_candidates(db,None,1000,{"device","network_discovery"})
        elif job_type=="expired_warranty_notifications":
            from datetime import date
            count=db.query(ConfigurationItem).filter(ConfigurationItem.status!="archived",ConfigurationItem.warranty_date<date.today()).limit(1000).count()
            if count:
                from app.services.cmdb_notification_service import notify_cmdb
                notify_cmdb(db,"HIOP CMDB warranty review",f"{count} configuration items have expired warranty dates.")
        db.commit()
    except Exception:db.rollback();logger.exception("CMDB scheduler job failed job_type=%s",job_type)
    finally:db.close()


def reconcile_cmdb_jobs() -> dict[str,int]:
    if not settings.scheduler_enabled:return {"registered":0,"removed":0}
    if not scheduler.running:scheduler.start()
    expected=set()
    for job_type,minutes in CMDB_JOB_INTERVALS.items():
        job_id=cmdb_job_id(job_type);expected.add(job_id);scheduler.add_job(scheduled_cmdb_job,"interval",minutes=minutes,id=job_id,args=[job_type],replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=min(minutes*60,3600))
    removed=0
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(CMDB_JOB_PREFIX) and job.id not in expected:scheduler.remove_job(job.id);removed+=1
    return {"registered":len(expected),"removed":removed}


def snmp_job_id(target_id: str, group: str) -> str:
    return f"{SNMP_JOB_PREFIX}{target_id}_{group}"


def _snmp_schedulable(target, config, credential) -> bool:
    return bool(settings.snmp_enabled and target and target.enabled and target.polling_enabled
                and config and config.enabled and credential and credential.enabled)


def register_snmp_jobs(target_id: str) -> int:
    if not settings.scheduler_enabled:
        return 0
    db = SessionLocal()
    try:
        target = db.get(SNMPTarget, target_id)
        config = db.scalar(select(SNMPPollingConfiguration).where(SNMPPollingConfiguration.target_id == target_id))
        credential = db.get(SNMPCredential, target.credential_id) if target else None
        if not _snmp_schedulable(target, config, credential):
            remove_snmp_jobs(target_id)
            return 0
        if not scheduler.running:
            scheduler.start()
        count = 0
        for group, (enabled_field, interval_field, _) in SNMP_GROUPS.items():
            job_id = snmp_job_id(target_id, group)
            if not getattr(config, enabled_field):
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                continue
            interval = min(settings.snmp_maximum_polling_interval_seconds,
                           max(settings.snmp_minimum_polling_interval_seconds, getattr(config, interval_field)))
            scheduler.add_job(
                scheduled_snmp_poll, "interval", seconds=interval, jitter=config.jitter_seconds,
                id=job_id, args=[target_id, group], replace_existing=True, max_instances=1,
                coalesce=True, misfire_grace_time=min(interval, 300),
            )
            count += 1
        config.last_scheduler_reconciliation_at = datetime.now(timezone.utc)
        db.commit()
        return count
    finally:
        db.close()


def update_snmp_jobs(target_id: str) -> int:
    return register_snmp_jobs(target_id)


def remove_snmp_jobs(target_id: str) -> int:
    count = 0
    prefix = f"{SNMP_JOB_PREFIX}{target_id}_"
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(prefix):
            scheduler.remove_job(job.id)
            count += 1
    return count


def pause_target_jobs(target_id: str) -> int:
    jobs = [job for job in scheduler.get_jobs() if job.id.startswith(f"{SNMP_JOB_PREFIX}{target_id}_")]
    for job in jobs:
        scheduler.pause_job(job.id)
    return len(jobs)


def resume_target_jobs(target_id: str) -> int:
    return update_snmp_jobs(target_id)


def recover_stale_snmp_runs(db=None) -> int:
    owns = db is None
    db = db or SessionLocal()
    try:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.snmp_stale_run_timeout_seconds)
        rows = db.scalars(select(SNMPPollRun).where(
            SNMPPollRun.status.in_(("pending", "running")), SNMPPollRun.started_at < threshold
        )).all()
        for run in rows:
            run.status, run.completed_at = "failed", datetime.now(timezone.utc)
            run.error_category, run.error_summary = "configuration_error", "Recovered stale poll after scheduler startup."
        if rows:
            db.commit()
        return len(rows)
    finally:
        if owns:
            db.close()


def reconcile_snmp_jobs(db=None) -> dict[str, int]:
    owns = db is None
    db = db or SessionLocal()
    expected, registered, removed = set(), 0, 0
    try:
        targets = db.scalars(select(SNMPTarget)).all()
        for target in targets:
            config = db.scalar(select(SNMPPollingConfiguration).where(SNMPPollingConfiguration.target_id == target.id))
            credential = db.get(SNMPCredential, target.credential_id)
            if _snmp_schedulable(target, config, credential):
                for group, (enabled_field, _, _) in SNMP_GROUPS.items():
                    if getattr(config, enabled_field):
                        expected.add(snmp_job_id(str(target.id), group))
                registered += register_snmp_jobs(str(target.id))
            else:
                removed += remove_snmp_jobs(str(target.id))
        for job in list(scheduler.get_jobs()):
            if job.id.startswith(SNMP_JOB_PREFIX) and job.id not in expected:
                scheduler.remove_job(job.id)
                removed += 1
        return {"registered": registered, "removed": removed, "expected": len(expected)}
    finally:
        if owns:
            db.close()


def scheduled_snmp_poll(target_id: str, group: str):
    db = SessionLocal()
    actor = SimpleNamespace(id=None, username="scheduler")
    try:
        target = db.get(SNMPTarget, target_id)
        config = db.scalar(select(SNMPPollingConfiguration).where(SNMPPollingConfiguration.target_id == target_id))
        credential = db.get(SNMPCredential, target.credential_id) if target else None
        if not _snmp_schedulable(target, config, credential):
            remove_snmp_jobs(target_id)
            return
        _, _, poll_type = SNMP_GROUPS[group]
        from app.services.snmp_polling_service import SNMPPollingService
        service = SNMPPollingService(db)
        run = service.create_poll_run(target.id, actor, poll_type=poll_type, trigger_type="scheduled")
        service.execute_poll(run.id, actor)
    except Exception:
        db.rollback()
        logger.exception("Scheduled SNMP poll failed target_id=%s group=%s", target_id, group)
    finally:
        db.close()


def scheduled_snmp_retention_cleanup():
    db = SessionLocal()
    try:
        from app.services.snmp_operational_service import SNMPOperationalService
        SNMPOperationalService(db).cleanup(SimpleNamespace(username="scheduler"),
                                           settings.snmp_metric_retention_days,
                                           settings.snmp_poll_run_retention_days)
    except Exception:
        db.rollback()
        logger.exception("Scheduled SNMP retention cleanup failed")
    finally:
        db.close()


def topology_job_id(topology_id: str, job_type: str) -> str:
    return f"{TOPOLOGY_JOB_PREFIX}{topology_id}_{job_type}"


def remove_topology_jobs(topology_id: str) -> int:
    count = 0
    for job_type in TOPOLOGY_JOB_TYPES:
        job = scheduler.get_job(topology_job_id(topology_id, job_type))
        if job:
            scheduler.remove_job(job.id); count += 1
    return count


def register_topology_jobs(topology_id: str) -> int:
    if not settings.scheduler_enabled:
        return 0
    db = SessionLocal()
    try:
        topology = db.get(Topology, topology_id)
        config = db.scalar(select(TopologyScheduleConfiguration).where(TopologyScheduleConfiguration.topology_id == topology_id))
        if not topology or not topology.enabled or not config or not config.enabled:
            remove_topology_jobs(topology_id)
            return 0
        if not scheduler.running:
            scheduler.start()
        specifications = {
            "collection": (config.neighbor_collection_enabled, config.neighbor_collection_interval_minutes * 60),
            "inference": (config.inference_enabled, config.inference_interval_minutes * 60),
            "snapshot": (config.snapshot_enabled, config.snapshot_interval_hours * 3600),
            "changes": (config.change_evaluation_enabled, config.change_evaluation_interval_minutes * 60),
            "health": (config.alerting_enabled, max(900, config.change_evaluation_interval_minutes * 60)),
        }
        count = 0
        for job_type, (enabled, seconds) in specifications.items():
            job_id = topology_job_id(topology_id, job_type)
            if not enabled:
                if scheduler.get_job(job_id): scheduler.remove_job(job_id)
                continue
            scheduler.add_job(
                scheduled_topology_operation, "interval", seconds=seconds,
                jitter=min(config.jitter_seconds, max(0, seconds // 4)),
                id=job_id, args=[topology_id, job_type], replace_existing=True,
                max_instances=1, coalesce=True, misfire_grace_time=min(seconds, 300),
            )
            count += 1
        config.last_scheduler_reconciliation_at = datetime.now(timezone.utc)
        db.commit()
        return count
    finally:
        db.close()


def update_topology_jobs(topology_id: str) -> int:
    return register_topology_jobs(topology_id)


def pause_topology_jobs(topology_id: str) -> int:
    jobs = [job for job in scheduler.get_jobs() if job.id.startswith(f"{TOPOLOGY_JOB_PREFIX}{topology_id}_")]
    for job in jobs: scheduler.pause_job(job.id)
    return len(jobs)


def resume_topology_jobs(topology_id: str) -> int:
    return register_topology_jobs(topology_id)


def recover_stale_topology_runs(db=None) -> int:
    owns = db is None
    db = db or SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        rows = db.scalars(select(TopologyOperationalRun).where(
            TopologyOperationalRun.status.in_(("pending", "running")),
            TopologyOperationalRun.started_at < cutoff,
        )).all()
        for run in rows:
            run.status = "failed"; run.completed_at = datetime.now(timezone.utc)
            run.error_summary = "Recovered stale topology operation after scheduler startup."
        stale_inference = db.scalars(select(TopologyInferenceRun).where(
            TopologyInferenceRun.status.in_(("pending", "running")),
            TopologyInferenceRun.started_at < cutoff,
        )).all()
        for run in stale_inference:
            run.status = "failed"; run.completed_at = datetime.now(timezone.utc)
            run.error_summary = "Recovered stale inference after scheduler startup."
        if rows or stale_inference: db.commit()
        return len(rows) + len(stale_inference)
    finally:
        if owns: db.close()


def reconcile_topology_jobs(db=None) -> dict[str, int]:
    owns = db is None
    db = db or SessionLocal()
    expected, registered, removed = set(), 0, 0
    try:
        configs = db.scalars(select(TopologyScheduleConfiguration)).all()
        for config in configs:
            topology = db.get(Topology, config.topology_id)
            if topology and topology.enabled and config.enabled:
                flags = {
                    "collection": config.neighbor_collection_enabled, "inference": config.inference_enabled,
                    "snapshot": config.snapshot_enabled, "changes": config.change_evaluation_enabled,
                    "health": config.alerting_enabled,
                }
                expected.update(topology_job_id(str(config.topology_id), kind) for kind, enabled in flags.items() if enabled)
                registered += register_topology_jobs(str(config.topology_id))
            else:
                removed += remove_topology_jobs(str(config.topology_id))
        for job in list(scheduler.get_jobs()):
            if job.id.startswith(TOPOLOGY_JOB_PREFIX) and job.id != TOPOLOGY_CLEANUP_JOB_ID and job.id not in expected:
                scheduler.remove_job(job.id); removed += 1
        return {"registered": registered, "removed": removed, "expected": len(expected)}
    finally:
        if owns: db.close()


def scheduled_topology_operation(topology_id: str, job_type: str):
    db = SessionLocal()
    actor = SimpleNamespace(id=None, username="scheduler")
    started = datetime.now(timezone.utc)
    run = None
    try:
        topology = db.get(Topology, topology_id)
        config = db.scalar(select(TopologyScheduleConfiguration).where(TopologyScheduleConfiguration.topology_id == topology_id))
        if not topology or not topology.enabled or not config or not config.enabled:
            remove_topology_jobs(topology_id); return
        active = db.scalar(select(TopologyOperationalRun).where(
            TopologyOperationalRun.topology_id == topology_id,
            TopologyOperationalRun.status.in_(("pending", "running")),
        ))
        if active:
            logger.info("Skipped overlapping topology job topology_id=%s type=%s", topology_id, job_type)
            return
        run = TopologyOperationalRun(topology_id=topology.id, run_type=job_type, trigger_type="scheduled")
        db.add(run); db.commit(); db.refresh(run)
        from app.services.topology_operational_service import TopologyOperationalService
        operations = TopologyOperationalService(db)
        if job_type == "collection":
            from app.services.topology_neighbor_collection_service import TopologyNeighborCollectionService
            target_ids = db.scalars(select(TopologyNode.snmp_target_id).where(
                TopologyNode.topology_id == topology.id, TopologyNode.snmp_target_id.is_not(None)
            ).distinct().limit(config.maximum_targets_per_run)).all()
            run.target_count = len(target_ids)
            for target_id in target_ids:
                target = db.get(SNMPTarget, target_id)
                if not target or not target.enabled:
                    run.failure_count += 1; continue
                result = TopologyNeighborCollectionService(db).collect(topology, target, config.protocol_mode, config.dry_run_default, actor)
                result.trigger_type = "scheduled"
                if result.status in {"completed", "partial"}: run.success_count += 1
                else: run.failure_count += 1
                db.commit()
        elif job_type == "inference":
            from app.schemas.topology_inference import InferenceRequest
            result = __import__("app.services.topology_inference_service", fromlist=["TopologyInferenceService"]).TopologyInferenceService(db).run(
                topology, InferenceRequest(dry_run=config.dry_run_default), actor
            )
            run.conflicts = result.conflicts_detected
        elif job_type == "snapshot":
            from app.schemas.topology import SnapshotWrite
            snapshot = TopologyService(db).snapshot(topology, SnapshotWrite(name=f"Scheduled {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", snapshot_type="manual"), actor)
            run.snapshot_id = snapshot.id
        elif job_type == "changes":
            result = operations.evaluate_changes(topology.id, actor=actor.username)
            run.changes_found = result["created"]
        elif job_type == "health":
            result = operations.evaluate_alerts(topology.id, actor=actor.username)
            run.alerts_created = result["opened"]
        run.status = "partial" if run.failure_count else "completed"
    except Exception:
        db.rollback()
        run = db.get(TopologyOperationalRun, run.id) if run else None
        if run:
            run.status = "failed"; run.error_summary = "Scheduled topology operation failed safely."
        logger.exception("Scheduled topology operation failed topology_id=%s type=%s", topology_id, job_type)
    finally:
        if run:
            run.completed_at = datetime.now(timezone.utc)
            run.duration_ms = int((run.completed_at - started).total_seconds() * 1000)
            db.commit()
        db.close()


def scheduled_topology_retention_cleanup():
    db = SessionLocal()
    try:
        from app.services.topology_operational_service import TopologyOperationalService
        TopologyOperationalService(db).cleanup(SimpleNamespace(username="scheduler"))
    except Exception:
        db.rollback(); logger.exception("Scheduled topology retention cleanup failed")
    finally:
        db.close()


def analytics_job_id(job_type: str) -> str:
    if job_type not in ANALYTICS_JOB_TYPES:
        raise ValueError("Unsupported analytics job type.")
    return f"{ANALYTICS_JOB_PREFIX}{job_type.lower()}"


def remove_analytics_jobs() -> int:
    jobs = [job for job in scheduler.get_jobs() if job.id.startswith(ANALYTICS_JOB_PREFIX)]
    for job in jobs:
        scheduler.remove_job(job.id)
    return len(jobs)


def register_analytics_jobs(db=None) -> int:
    owns = db is None
    db = db or SessionLocal()
    try:
        config = db.scalar(select(AnalyticsScheduleConfiguration).limit(1))
        if not settings.analytics_enabled or not config or not config.enabled or config.paused:
            remove_analytics_jobs()
            return 0
        if not scheduler.running:
            scheduler.start()
        specs = {
            "aggregate": (config.aggregate_enabled, config.aggregate_interval_minutes * 60),
            "availability": (config.availability_enabled, config.availability_interval_minutes * 60),
            "health_score": (config.health_score_enabled, config.health_score_interval_minutes * 60),
            "capacity": (config.capacity_enabled, config.capacity_interval_minutes * 60),
            "SLA": (config.sla_enabled, config.sla_interval_hours * 3600),
            "reliability": (config.reliability_enabled, config.reliability_interval_hours * 3600),
            "data_quality": (config.data_quality_enabled, config.data_quality_interval_minutes * 60),
            "baseline": (getattr(config, "baseline_enabled", False), getattr(config, "baseline_interval_hours", 24) * 3600),
            "anomaly": (getattr(config, "anomaly_detection_enabled", False), getattr(config, "anomaly_interval_minutes", 15) * 60),
            "correlation": (getattr(config, "correlation_enabled", False), getattr(config, "correlation_interval_minutes", 15) * 60),
            "insight": (getattr(config, "insight_refresh_enabled", False), getattr(config, "insight_interval_minutes", 30) * 60),
            "anomaly_recovery": (getattr(config, "anomaly_detection_enabled", False), getattr(config, "anomaly_recovery_interval_minutes", 15) * 60),
            "retention_cleanup": (config.retention_cleanup_enabled, config.retention_cleanup_interval_hours * 3600),
        }
        expected = set()
        for job_type, (enabled, seconds) in specs.items():
            job_id = analytics_job_id(job_type)
            if not enabled:
                if scheduler.get_job(job_id): scheduler.remove_job(job_id)
                continue
            expected.add(job_id)
            scheduler.add_job(
                scheduled_analytics_operation, "interval", seconds=seconds,
                jitter=min(config.jitter_seconds, max(0, seconds // 4)),
                id=job_id, args=[job_type], replace_existing=True,
                max_instances=1, coalesce=True, misfire_grace_time=min(seconds, 300),
            )
        for job in list(scheduler.get_jobs()):
            if job.id.startswith(ANALYTICS_JOB_PREFIX) and job.id not in expected:
                scheduler.remove_job(job.id)
        config.last_reconciled_at = datetime.now(timezone.utc)
        db.commit()
        return len(expected)
    finally:
        if owns: db.close()


def update_analytics_jobs(db=None) -> int:
    return register_analytics_jobs(db)


def reconcile_analytics_jobs(db=None) -> dict[str, int]:
    count = register_analytics_jobs(db)
    return {"registered": count, "expected": count}


def pause_analytics_jobs(db=None) -> int:
    owns = db is None
    db = db or SessionLocal()
    try:
        config = db.scalar(select(AnalyticsScheduleConfiguration).limit(1))
        if config:
            config.paused = True; db.commit()
        return remove_analytics_jobs()
    finally:
        if owns: db.close()


def resume_analytics_jobs(db=None) -> int:
    owns = db is None
    db = db or SessionLocal()
    try:
        config = db.scalar(select(AnalyticsScheduleConfiguration).limit(1))
        if config:
            config.paused = False; db.commit()
        return register_analytics_jobs(db)
    finally:
        if owns: db.close()


def recover_stale_analytics_runs(db=None) -> int:
    owns = db is None
    db = db or SessionLocal()
    try:
        config = db.scalar(select(AnalyticsScheduleConfiguration).limit(1))
        timeout = config.stale_run_timeout_minutes if config else 60
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout)
        rows = db.scalars(select(AnalyticsRun).where(
            AnalyticsRun.status.in_(("pending", "running", "retry_pending")),
            AnalyticsRun.started_at < cutoff,
        )).all()
        for run in rows:
            run.status = "failed"; run.completed_at = datetime.now(timezone.utc)
            run.stale_recovery_status = "failed_on_startup"
            run.error_summary = "Recovered stale analytics run after scheduler startup."
        if rows: db.commit()
        return len(rows)
    finally:
        if owns: db.close()


def scheduled_analytics_operation(job_type: str):
    db = SessionLocal()
    try:
        config = db.scalar(select(AnalyticsScheduleConfiguration).limit(1))
        if not config or not config.enabled or config.paused:
            return
        if db.scalar(select(AnalyticsRun).where(
            AnalyticsRun.status.in_(("pending", "running", "retry_pending")),
            AnalyticsRun.run_type == job_type,
        )):
            logger.info("Skipped overlapping analytics job type=%s", job_type)
            return
        end = datetime.now(timezone.utc)
        run = AnalyticsRun(
            run_type=job_type, scope_type="global",
            period_start=end - timedelta(minutes=config.default_lookback_minutes),
            period_end=end, trigger_type="scheduled", job_id=analytics_job_id(job_type),
            schedule_type=job_type, bucket_sizes=["5_minutes"], dry_run=False,
        )
        cleanup_batch_size = config.batch_size
        db.add(run); db.commit(); run_id = run.id
    except Exception:
        db.rollback(); logger.exception("Failed to create scheduled analytics run type=%s", job_type)
        db.close(); return
    db.close()
    if job_type == "retention_cleanup":
        cleanup_db = SessionLocal()
        try:
            from app.services.analytics_operational_service import AnalyticsOperationalService
            active = cleanup_db.get(AnalyticsRun, run_id); active.status = "running"
            result = AnalyticsOperationalService(cleanup_db).cleanup(cleanup_batch_size)
            active.status = "completed"; active.result_summary = result
            active.completed_at = datetime.now(timezone.utc); cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
            active = cleanup_db.get(AnalyticsRun, run_id)
            if active:
                active.status = "failed"; active.completed_at = datetime.now(timezone.utc)
                active.error_summary = "Scheduled analytics cleanup failed safely."
                cleanup_db.commit()
            logger.exception("Scheduled analytics cleanup failed")
        finally:
            cleanup_db.close()
    else:
        from app.services.analytics_run_service import execute_analytics_run
        execute_analytics_run(run_id)


def ad_sync_job_id(connection_id: str) -> str:
    return f"{AD_JOB_PREFIX}{connection_id}"


def _ad_schedulable(connection, config) -> bool:
    return bool(
        settings.active_directory_enabled
        and connection.enabled
        and config
        and config.enabled
        and (config.sync_users_enabled or config.sync_computers_enabled or config.sync_groups_enabled)
        and (connection.authentication_method == "anonymous" or connection.encrypted_bind_secret)
    )


def register_ad_sync_job(connection_id: str, interval_minutes: int | None = None) -> bool:
    if not settings.scheduler_enabled:
        return False
    db = SessionLocal()
    try:
        connection = db.get(ActiveDirectoryConnection, connection_id)
        config = db.scalar(select(ActiveDirectorySyncConfiguration).where(
            ActiveDirectorySyncConfiguration.connection_id == connection_id
        ))
        if not connection or not _ad_schedulable(connection, config):
            remove_ad_sync_job(connection_id)
            return False
        if not scheduler.running:
            scheduler.start()
        scheduler.add_job(
            scheduled_ad_sync,
            trigger="interval",
            minutes=min(
                settings.ad_maximum_sync_interval_minutes,
                max(
                    settings.ad_minimum_sync_interval_minutes,
                    interval_minutes or config.sync_interval_minutes,
                ),
            ),
            id=ad_sync_job_id(connection_id),
            args=[connection_id],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        logger.info("Registered AD sync job connection_id=%s", connection_id)
        return True
    finally:
        db.close()


def update_ad_sync_job(connection_id: str) -> bool:
    return register_ad_sync_job(connection_id)


def remove_ad_sync_job(connection_id: str) -> bool:
    job = scheduler.get_job(ad_sync_job_id(connection_id))
    if job:
        scheduler.remove_job(job.id)
        logger.info("Removed AD sync job connection_id=%s", connection_id)
        return True
    return False


def recover_stale_ad_runs(db=None) -> int:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        threshold = datetime.now(timezone.utc) - timedelta(
            minutes=settings.ad_sync_stale_run_timeout_minutes
        )
        stale = db.scalars(select(ActiveDirectorySyncRun).where(
            ActiveDirectorySyncRun.status.in_(("pending", "running")),
            ActiveDirectorySyncRun.started_at < threshold,
        )).all()
        for run in stale:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_summary = "Recovered stale synchronization after scheduler startup."
        if stale:
            db.commit()
            logger.warning("Recovered stale AD sync runs count=%s", len(stale))
        return len(stale)
    finally:
        if owns_session:
            db.close()


def reconcile_ad_sync_jobs(db=None) -> dict[str, int]:
    owns_session = db is None
    db = db or SessionLocal()
    registered = removed = 0
    try:
        connections = db.scalars(select(ActiveDirectoryConnection)).all()
        configured_ids = set()
        for connection in connections:
            config = db.scalar(select(ActiveDirectorySyncConfiguration).where(
                ActiveDirectorySyncConfiguration.connection_id == connection.id
            ))
            if _ad_schedulable(connection, config):
                configured_ids.add(str(connection.id))
                if register_ad_sync_job(str(connection.id), config.sync_interval_minutes):
                    registered += 1
            elif remove_ad_sync_job(str(connection.id)):
                removed += 1
        for job in list(scheduler.get_jobs()):
            if job.id.startswith(AD_JOB_PREFIX):
                connection_id = job.id.removeprefix(AD_JOB_PREFIX)
                if connection_id not in configured_ids:
                    scheduler.remove_job(job.id)
                    removed += 1
        return {"registered": registered, "removed": removed}
    finally:
        if owns_session:
            db.close()


def scheduled_ad_sync(connection_id: str):
    db = SessionLocal()
    try:
        connection = db.get(ActiveDirectoryConnection, connection_id)
        config = db.scalar(select(ActiveDirectorySyncConfiguration).where(
            ActiveDirectorySyncConfiguration.connection_id == connection_id
        ))
        if not connection or not _ad_schedulable(connection, config):
            remove_ad_sync_job(connection_id)
            return
        object_types = [
            name for name, enabled in (
                ("user", config.sync_users_enabled),
                ("computer", config.sync_computers_enabled),
                ("group", config.sync_groups_enabled),
            ) if enabled
        ]
        from app.services.active_directory_sync_service import ActiveDirectorySynchronizationService
        ActiveDirectorySynchronizationService(db).start(
            connection_id,
            SimpleNamespace(id=None, username="scheduler"),
            sync_mode=settings.ad_sync_default_mode,
            dry_run=config.dry_run_default,
            object_types=object_types,
            limit=settings.ad_maximum_objects_per_sync,
        )
    except Exception:
        db.rollback()
        logger.exception("Scheduled AD sync failed connection_id=%s", connection_id)
    finally:
        db.close()


def configure_scheduler(enabled: bool, interval_minutes: int) -> None:
    from app.core.config import settings
    if not settings.scheduler_enabled:
        return
    if not scheduler.running:
        scheduler.start()
    if not enabled:
        if scheduler.get_job("automatic_network_scan"):
            scheduler.remove_job("automatic_network_scan")
        return
    scheduler.add_job(scheduled_network_scan, trigger="interval", minutes=interval_minutes, id="automatic_network_scan", replace_existing=True, max_instances=1)


def configure_discovery_scheduler(enabled: bool, interval_minutes: int) -> None:
    from app.core.config import settings
    if not settings.scheduler_enabled:
        return
    if not scheduler.running:
        scheduler.start()
    if not enabled:
        if scheduler.get_job("automatic_discovery"):
            scheduler.remove_job("automatic_discovery")
        return
    scheduler.add_job(
        scheduled_discovery,
        trigger="interval",
        minutes=interval_minutes,
        id="automatic_discovery",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def scheduled_network_scan():
    db = SessionLocal()

    try:
        result = scan_all_devices(db)

        logger.info("Automatic network scan completed total=%s online=%s offline=%s", result["total_devices"], result["online"], result["offline"])

    except Exception:
        db.rollback()
        logger.exception("Automatic network scan failed")

    finally:
        db.close()


def scheduled_discovery():
    db = SessionLocal()
    try:
        from app.discovery.network import parse_networks
        from app.services.discovery_service import DiscoveryService
        from app.services.settings_service import read_discovery
        config = read_discovery(db)
        if not config["enabled"]:
            return
        for network in parse_networks(config["authorized_cidr_ranges"]):
            DiscoveryService(db, config=config).discover_range(
                str(network), trigger_type="scheduled", audit_actor="scheduler"
            )
    except Exception:
        db.rollback()
        logger.exception("Automatic discovery failed")
    finally:
        db.close()


def scheduled_problem_management(job_type: str):
    """Deterministic reminders and review suggestions; never creates a problem or root cause."""
    db=SessionLocal()
    try:
        now_at=datetime.now(timezone.utc)
        if job_type=="recurring_incident_detection":
            incidents=db.query(OperationalIncident).filter(OperationalIncident.created_at>=now_at-timedelta(days=30)).limit(5000).all(); groups={}
            for incident in incidents:
                key=incident.correlation_key or f"{incident.property_id}:{incident.technology_service_id}:{incident.incident_type}"
                groups.setdefault(key,[]).append(incident)
            for key,rows in groups.items():
                if len(rows)>=3 and not db.query(ProblemCorrelationSuggestion).filter_by(correlation_key=key,status="suggested").first():
                    import json
                    db.add(ProblemCorrelationSuggestion(property_id=rows[0].property_id,correlation_key=key,source_type="incident",source_ids=json.dumps([str(r.id) for r in rows]),occurrence_count=len(rows),threshold=3,rationale=f"{len(rows)} incidents share a deterministic correlation key within 30 days."))
        elif job_type=="problem_aging_alerts":
            db.query(Problem).filter(~Problem.status.in_(("resolved","closed")),Problem.created_at<now_at-timedelta(days=30)).update({Problem.review_date:now_at},synchronize_session=False)
        elif job_type=="capa_due_reminders":
            db.query(ActionTask).filter(ActionTask.status=="pending",ActionTask.due_at<now_at).update({ActionTask.status:"overdue"},synchronize_session=False)
        elif job_type=="known_error_review_reminders":
            db.query(KnownError).filter(KnownError.status=="published",KnownError.updated_at<now_at-timedelta(days=180)).update({KnownError.status:"review_due"},synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback(); logger.exception("Problem Management scheduled job failed type=%s",job_type)
    finally: db.close()


def reconcile_problem_jobs():
    if not settings.scheduler_enabled:return 0
    for job_type,minutes in PROBLEM_JOB_INTERVALS.items():scheduler.add_job(scheduled_problem_management,"interval",minutes=minutes,id=f"problem_management_{job_type}",args=[job_type],replace_existing=True,max_instances=1,coalesce=True)
    return len(PROBLEM_JOB_INTERVALS)

def scheduled_asset_management(job_type: str):
    """Finance-aware scheduled maintenance; records flags and calculations, never purchases."""
    db=SessionLocal()
    try:
        now_at=datetime.now(timezone.utc); today=now_at.date(); soon=today+timedelta(days=90)
        if job_type=="warranty_reminders":db.query(Warranty).filter(Warranty.status=="active",Warranty.end_date.between(today,soon)).update({Warranty.status:"renewal_review"},synchronize_session=False)
        elif job_type=="contract_renewal_reminders":db.query(Contract).filter(Contract.status=="active",Contract.end_date.between(today,soon)).update({Contract.status:"renewal_review"},synchronize_session=False)
        elif job_type=="license_renewal_reminders":db.query(SoftwareLicense).filter(SoftwareLicense.status=="active",SoftwareLicense.renewal_date.between(today,soon)).update({SoftwareLicense.status:"renewal_review"},synchronize_session=False)
        elif job_type=="asset_lifecycle_reviews":db.query(EnterpriseAsset).filter(EnterpriseAsset.end_of_life<=today,~EnterpriseAsset.lifecycle_stage.in_(("retired","disposed","archived"))).update({EnterpriseAsset.status:"lifecycle_review"},synchronize_session=False)
        elif job_type=="depreciation_recalculation":
            from app.api.v1.asset_management import depreciation
            for asset in db.query(EnterpriseAsset).filter(~EnterpriseAsset.lifecycle_stage.in_(("disposed","archived"))).limit(10000):values=depreciation(asset,today);asset.depreciation_value=values["depreciation"];asset.current_value=values["current_value"]
        elif job_type=="vendor_score_aggregation":
            for vendor in db.query(Vendor).all():
                score=db.query(func.avg(VendorPerformance.overall_score)).filter_by(vendor_id=vendor.id).scalar()
                if score is not None:vendor.rating=score
        db.commit()
    except Exception:db.rollback();logger.exception("Asset Management scheduled job failed type=%s",job_type)
    finally:db.close()

def reconcile_asset_jobs():
    if not settings.scheduler_enabled:return 0
    for job_type,minutes in ASSET_JOB_INTERVALS.items():scheduler.add_job(scheduled_asset_management,"interval",minutes=minutes,id=f"asset_management_{job_type}",args=[job_type],replace_existing=True,max_instances=1,coalesce=True)
    return len(ASSET_JOB_INTERVALS)

def scheduled_business_intelligence(job_type: str):
    """Deterministic executive aggregation and explicitly configured report delivery."""
    import hashlib,json
    db=SessionLocal()
    try:
        from app.api.v1.business_intelligence import source_value
        from app.services.business_intelligence_service import calculate_formula,linear_forecast,trend
        now_at=datetime.now(timezone.utc)
        if job_type=="kpi_recalculation":
            for kpi in db.query(KPI).filter_by(enabled=True).limit(1000):
                definition=db.get(KPIDefinition,kpi.definition_id)
                if not definition or not definition.enabled:continue
                inputs={key:str(source_value(db,key,kpi.scope_id)) for key in json.loads(definition.source_keys)};value=calculate_formula(definition.operation,list(inputs.values()));db.add(KPIValue(kpi_id=kpi.id,value=value,period_start=now_at-timedelta(hours=1),period_end=now_at,frequency="hourly",status="calculated",inputs=json.dumps(inputs,sort_keys=True)))
        elif job_type=="snapshot_generation":
            values={str(kpi.id):str((db.query(KPIValue).filter_by(kpi_id=kpi.id).order_by(KPIValue.period_end.desc()).first() or type("V",(),{"value":0})()).value) for kpi in db.query(KPI).filter_by(enabled=True).limit(1000)};raw=json.dumps(values,sort_keys=True);db.add(KPISnapshot(scope_type="corporate",period_start=now_at-timedelta(days=1),period_end=now_at,frequency="daily",values=raw,checksum=hashlib.sha256(raw.encode()).hexdigest()))
        elif job_type in ("trend_aggregation","capacity_recalculation","dashboard_cache_refresh"):
            kpi_rows={}
            for kpi in db.query(KPI).filter_by(enabled=True).limit(200):
                rows=list(reversed(db.query(KPIValue).filter_by(kpi_id=kpi.id).order_by(KPIValue.period_end.desc()).limit(12).all()));series=[r.value for r in rows];kpi_rows[str(kpi.id)]={"latest":str(series[-1]) if series else "0","trend":trend(series),"forecast":[str(x) for x in linear_forecast(series,3)]}
            for dashboard in db.query(ExecutiveDashboard).filter_by(enabled=True):
                cache=db.query(DashboardCache).filter_by(dashboard_id=dashboard.id,scope_type="corporate",scope_id=None).first() or DashboardCache(dashboard_id=dashboard.id,scope_type="corporate",scope_id=None,payload="{}",expires_at=now_at);db.add(cache);cache.payload=json.dumps({"kpis":kpi_rows,"generated_at":now_at.isoformat()},default=str);cache.generated_at=now_at;cache.expires_at=now_at+timedelta(minutes=20)
        elif job_type in ("report_scheduling","email_distribution"):
            due=db.query(ScheduledReport).filter_by(enabled=True).filter(ScheduledReport.next_run_at<=now_at).limit(100).all()
            for schedule in due:
                db.add(ReportExecution(report_id=schedule.report_id,status="completed",format=schedule.format,parameters="{}",trigger_type="scheduled",completed_at=now_at));schedule.last_run_at=now_at;days={"daily":1,"weekly":7,"monthly":30,"quarterly":90,"yearly":365}[schedule.frequency];schedule.next_run_at=now_at+timedelta(days=days)
                if job_type=="email_distribution" and settings.email_address and settings.email_password:
                    from app.services.email_service import send_email
                    for recipient in db.query(ReportRecipient).filter_by(scheduled_report_id=schedule.id,enabled=True):send_email("HIOP scheduled executive report",f"Scheduled HIOP report {schedule.report_id} completed at {now_at.isoformat()}.",recipient.recipient_value)
        db.commit()
    except Exception:db.rollback();logger.exception("Business Intelligence scheduled job failed type=%s",job_type)
    finally:db.close()

def reconcile_bi_jobs():
    if not settings.scheduler_enabled:return 0
    for job_type,minutes in BI_JOB_INTERVALS.items():scheduler.add_job(scheduled_business_intelligence,"interval",minutes=minutes,id=f"business_intelligence_{job_type}",args=[job_type],replace_existing=True,max_instances=1,coalesce=True)
    return len(BI_JOB_INTERVALS)


def scheduled_multi_property(job_type: str):
    """Refresh governed enterprise state; never changes operational property data."""
    import json,hashlib
    db=SessionLocal();now_at=datetime.now(timezone.utc)
    try:
        if job_type=="organization_synchronization":
            for prop in db.query(Property).filter(Property.is_active.is_(True)).limit(10000):
                values={r.key:(r.value,"global",r.id,r.enforced) for r in db.query(GlobalSetting).filter_by(organization_id=prop.organization_id)};membership=db.query(PropertyHierarchyMembership).filter_by(property_id=prop.id).first();region_id=None
                if membership:
                    from app.models.multi_property import Country,PropertyGroup
                    region_id=db.query(Country.region_id).join(PropertyGroup,PropertyGroup.country_id==Country.id).filter(PropertyGroup.id==membership.property_group_id).scalar()
                for r in db.query(RegionalSetting).filter_by(region_id=region_id) if region_id else []:
                    if not values.get(r.key,(None,None,None,False))[3]:values[r.key]=(r.value,"region",r.id,False)
                for r in db.query(PropertySetting).filter_by(property_id=prop.id):
                    if not values.get(r.key,(None,None,None,False))[3]:values[r.key]=(r.value,"property",r.id,False)
                for key,(value,source,source_id,_) in values.items():
                    checksum=hashlib.sha256(f"{source}:{source_id}:{value}".encode()).hexdigest();item=db.query(InheritedSetting).filter_by(property_id=prop.id,key=key).first() or InheritedSetting(property_id=prop.id,key=key,effective_value=value,source_type=source,source_id=source_id,checksum=checksum);db.add(item);item.effective_value=value;item.source_type=source;item.source_id=source_id;item.checksum=checksum;item.calculated_at=now_at
        elif job_type=="policy_compliance_checks":
            for assignment in db.query(PolicyAssignment).filter(PolicyAssignment.effective_from<=now_at.date()).limit(5000):
                for property_id in property_ids_for_scope(db,assignment.scope_type,assignment.scope_id):
                    item=db.query(PolicyCompliance).filter_by(assignment_id=assignment.id,property_id=property_id).first()
                    if not item:db.add(PolicyCompliance(assignment_id=assignment.id,property_id=property_id,status="not_assessed",evidence="{}"))
        elif job_type in ("cross_property_kpi_aggregation","dashboard_cache_refresh","executive_report_generation"):
            property_count=db.query(Property).filter(Property.is_active.is_(True)).count();incident_count=db.query(OperationalIncident).filter(~OperationalIncident.status.in_(("resolved","closed"))).count();payload=json.dumps({"properties":property_count,"open_incidents":incident_count,"generated_at":now_at.isoformat()},sort_keys=True);item=db.query(ExecutiveOperationsCache).filter_by(scope_type="organization",scope_id=None).first() or ExecutiveOperationsCache(scope_type="organization",scope_id=None,payload=payload,checksum="",expires_at=now_at);db.add(item);item.payload=payload;item.checksum=hashlib.sha256(payload.encode()).hexdigest();item.generated_at=now_at;item.expires_at=now_at+timedelta(minutes=20)
        elif job_type=="notification_routing":
            db.query(GlobalNotification).filter(GlobalNotification.status=="draft",GlobalNotification.publish_at.isnot(None),GlobalNotification.publish_at<=now_at).update({GlobalNotification.status:"published"},synchronize_session=False);db.query(GlobalNotification).filter(GlobalNotification.status=="published",GlobalNotification.expires_at.isnot(None),GlobalNotification.expires_at<=now_at).update({GlobalNotification.status:"expired"},synchronize_session=False)
        db.commit()
    except Exception:db.rollback();logger.exception("Multi-property scheduled job failed type=%s",job_type)
    finally:db.close()


def reconcile_multi_property_jobs():
    if not settings.scheduler_enabled:return 0
    for job_type,minutes in MULTI_PROPERTY_JOB_INTERVALS.items():scheduler.add_job(scheduled_multi_property,"interval",minutes=minutes,id=f"multi_property_{job_type}",args=[job_type],replace_existing=True,max_instances=1,coalesce=True)
    return len(MULTI_PROPERTY_JOB_INTERVALS)

def scheduled_discovery_intelligence(job_type:str):
    """Safe orchestration: schedules bounded work and recalculates local evidence only."""
    db=SessionLocal();now_at=datetime.now(timezone.utc)
    try:
        if job_type in ("incremental_discovery","full_discovery"):
            for policy in db.query(DiscoveryPolicy).filter_by(enabled=True).all():
                for network_range in parse_json(policy.authorized_ranges,[]):
                    active=db.query(DiscoveryJob).filter_by(policy_id=policy.id,network_range=network_range).filter(DiscoveryJob.status.in_(("pending","running"))).first()
                    if not active:DiscoveryIntelligenceService(db).create_job(policy,network_range,"full" if job_type=="full_discovery" else "incremental","scheduled")
        elif job_type=="confidence_recalculation":
            for row in db.query(DiscoveryResult).limit(10000):
                score=confidence(x[0] for x in db.query(DiscoveryEvidence.evidence_type).filter_by(result_id=row.id).distinct());row.confidence_score=score["score"]
                import json
                row.confidence_explanation=json.dumps(score["contributions"]);row.review_status=review_status(row.confidence_score) if row.review_status not in ("manually_verified","ignored","false_positive","duplicate","retired") else row.review_status
        elif job_type=="vendor_database_updates":
            db.query(DiscoveryOUI).filter_by(source="bundled").update({DiscoveryOUI.version:now_at.strftime("%Y.%m")},synchronize_session=False)
        elif job_type=="device_aging":
            db.query(DiscoveryResult).filter(DiscoveryResult.last_seen_at<now_at-timedelta(days=90),~DiscoveryResult.review_status.in_(("retired","ignored","false_positive"))).update({DiscoveryResult.review_status:"retired"},synchronize_session=False)
        elif job_type=="stale_device_detection":
            db.query(DiscoveryResult).filter(DiscoveryResult.last_seen_at<now_at-timedelta(days=14),DiscoveryResult.review_status=="automatically_identified").update({DiscoveryResult.review_status:"needs_review"},synchronize_session=False)
        # topology_refresh and cmdb_synchronization deliberately consume only reviewed
        # records through their explicit APIs; schedulers never invent links or overwrite CIs.
        db.commit()
    except Exception:db.rollback();logger.exception("Discovery Intelligence scheduled job failed type=%s",job_type)
    finally:db.close()

def reconcile_discovery_intelligence_jobs():
    if not settings.scheduler_enabled:return 0
    for job_type,minutes in DISCOVERY_INTELLIGENCE_JOB_INTERVALS.items():scheduler.add_job(scheduled_discovery_intelligence,"interval",minutes=minutes,id=f"discovery_intelligence_{job_type}",args=[job_type],replace_existing=True,max_instances=1,coalesce=True)
    return len(DISCOVERY_INTELLIGENCE_JOB_INTERVALS)


def start_scheduler():
    if not settings.scheduler_enabled:
        logger.info("HIOP scheduler disabled by configuration")
        return
    if scheduler.running:
        return

    scheduler.start()
    db = SessionLocal()
    try:
        from app.models.system_setting import SystemSetting
        values = {row.key: row.value for row in db.query(SystemSetting).filter(SystemSetting.key.in_(["network.automatic_scanning", "network.scan_interval_minutes", "discovery.enabled", "discovery.interval_minutes"])).all()}
        configure_scheduler(values.get("network.automatic_scanning", "true") == "true", max(5, int(values.get("network.scan_interval_minutes", "5"))))
        recover_stale_automation_runs(db)
        reconcile_automation_jobs(db)
        scheduler.add_job(scheduled_automation_outbox,"interval",minutes=1,id=AUTOMATION_OUTBOX_JOB_ID,replace_existing=True,max_instances=1,coalesce=True)
        scheduler.add_job(scheduled_automation_retention,"cron",hour=4,id=AUTOMATION_RETENTION_JOB_ID,replace_existing=True,max_instances=1,coalesce=True)
        recover_stale_incident_runs(db)
        reconcile_incident_jobs()
        reconcile_discovery_intelligence_jobs()
    finally:
        db.close()
    logger.info("HIOP scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("HIOP scheduler stopped")
