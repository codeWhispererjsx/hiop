"""Manual analytics run lifecycle. Epic 6A registers no scheduler jobs."""
from datetime import datetime, timezone
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.analytics import AnalyticsMetricDefinition, AnalyticsRun
from app.services.analytics_aggregation_service import AnalyticsAggregationService
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager


def execute_analytics_run(run_id):
    db = SessionLocal(); started = datetime.now(timezone.utc)
    try:
        run = db.get(AnalyticsRun, run_id)
        if not run or run.status != "pending": return
        run.status = "running"; db.commit()
        manager.broadcast_from_thread({"type": "analytics_run_started", "run_id": str(run.id), "run_type": run.run_type})
        if run.cancellation_requested: run.status = "cancelled"
        elif run.dry_run:
            run.result_summary = {"dry_run": True, "enabled_metric_definitions": db.query(AnalyticsMetricDefinition).filter_by(enabled=True).count(), "persistence": False}
            run.status = "completed"
        elif run.run_type in {"aggregate", "full"}:
            definitions = db.scalars(select(AnalyticsMetricDefinition).where(AnalyticsMetricDefinition.enabled.is_(True)).limit(100)).all()
            for definition in definitions:
                if run.cancellation_requested: run.status = "cancelled"; break
                try:
                    rows = AnalyticsAggregationService(db).aggregate(definition, run.scope_id if run.scope_type != "global" else None, run.period_start, run.period_end, "1_hour", True)
                    run.aggregates_created += len(rows)
                except Exception:
                    db.rollback(); run = db.get(AnalyticsRun, run_id); run.errors_count += 1
            if run.status != "cancelled": run.status = "partial" if run.errors_count else "completed"
        else:
            run.result_summary = {"foundation": True, "run_type": run.run_type, "message": "No supported source entities were selected."}
            run.status = "completed"
        run.entities_processed = min(run.entities_requested, 1 if run.scope_id else 0)
        run.completed_at = datetime.now(timezone.utc); run.duration_ms = int((run.completed_at - started).total_seconds() * 1000)
        create_audit_log(db, "analytics-worker", f"ANALYTICS_RUN_{run.status.upper()}", "AnalyticsRun", str(run.id), f"Manual {run.run_type} analytics run finished with {run.errors_count} safe errors.")
        db.commit()
        manager.broadcast_from_thread({"type": f"analytics_run_{run.status}", "run_id": str(run.id), "run_type": run.run_type, "counts": {"aggregates": run.aggregates_created, "errors": run.errors_count}})
    except Exception:
        db.rollback(); run = db.get(AnalyticsRun, run_id)
        if run:
            run.status = "failed"; run.completed_at = datetime.now(timezone.utc); run.error_summary = "Analytics run failed safely."; db.commit()
        manager.broadcast_from_thread({"type": "analytics_run_failed", "run_id": str(run_id)})
    finally: db.close()
