import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

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
        if schedule.blackout_start and schedule.blackout_end and schedule.blackout_start<=now<=schedule.blackout_end:
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
            scheduler.add_job(scheduled_automation_workflow,"interval",minutes=row.interval_minutes,args=[str(row.id)],**common);registered+=1
        elif row.schedule_type=="one_time" and row.next_run_at and row.next_run_at>datetime.now(timezone.utc):
            scheduler.add_job(scheduled_automation_workflow,"date",run_date=row.next_run_at,args=[str(row.id)],**common);registered+=1
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(AUTOMATION_JOB_PREFIX) and job.id not in expected:scheduler.remove_job(job.id);removed+=1
    return {"registered":registered,"removed":removed}

def recover_stale_automation_runs(db,timeout_minutes: int=30) -> int:
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=timeout_minutes);rows=db.query(AutomationWorkflowRun).filter(AutomationWorkflowRun.trigger_type.in_(("scheduled","internal_event","retry")),AutomationWorkflowRun.status.in_(("pending","running")),AutomationWorkflowRun.created_at<cutoff).all()
    for row in rows:row.status="failed";row.error_summary="Recovered stale automation run after scheduler startup."
    if rows:db.commit()
    return len(rows)


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
        configure_discovery_scheduler(values.get("discovery.enabled", "false") == "true", max(15, int(values.get("discovery.interval_minutes", "60"))))
        recover_stale_ad_runs(db)
        reconcile_ad_sync_jobs(db)
        recover_stale_snmp_runs(db)
        reconcile_snmp_jobs(db)
        if settings.snmp_enabled:
            scheduler.add_job(scheduled_snmp_retention_cleanup, "cron", hour=settings.snmp_cleanup_hour_utc,
                              id=SNMP_CLEANUP_JOB_ID, replace_existing=True, max_instances=1, coalesce=True)
        recover_stale_topology_runs(db)
        reconcile_topology_jobs(db)
        scheduler.add_job(
            scheduled_topology_retention_cleanup, "cron", hour=3,
            id=TOPOLOGY_CLEANUP_JOB_ID, replace_existing=True,
            max_instances=1, coalesce=True,
        )
        recover_stale_analytics_runs(db)
        reconcile_analytics_jobs(db)
        recover_stale_automation_runs(db)
        reconcile_automation_jobs(db)
    finally:
        db.close()
    logger.info("HIOP scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("HIOP scheduler stopped")
