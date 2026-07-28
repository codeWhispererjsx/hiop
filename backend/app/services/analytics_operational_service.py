"""Incremental analytics orchestration, bounded backfill, quality and retention."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import settings
from app.models.analytics import (
    AnalyticsAggregate, AnalyticsCheckpoint, AnalyticsDataQualityRecord,
    AnalyticsMetricDefinition, AnalyticsRetentionPolicy, AnalyticsRun,
    AnalyticsScheduleConfiguration, CapacityAssessment, CapacityPolicy,
    EntityHealthScore, SLAMeasurement,
)
from app.services.analytics_aggregation_service import AnalyticsAggregationService, BUCKET_SECONDS
from app.services.analytics_capacity_service import AnalyticsCapacityService

UTC = timezone.utc
RUN_TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"completed", "partial", "failed", "cancelled", "retry_pending"},
    "retry_pending": {"running", "cancelled"},
    "completed": set(), "partial": set(), "failed": {"retry_pending"}, "cancelled": set(),
}


class AnalyticsOperationalService:
    def __init__(self, db):
        self.db = db

    def schedule(self):
        row = self.db.scalar(select(AnalyticsScheduleConfiguration).limit(1))
        if not row:
            row = AnalyticsScheduleConfiguration()
            self.db.add(row); self.db.flush()
        return row

    @staticmethod
    def transition(run, status):
        if status not in RUN_TRANSITIONS.get(run.status, set()):
            raise HTTPException(409, f"Invalid analytics run transition: {run.status} to {status}.")
        run.status = status

    def preview_backfill(self, payload):
        AnalyticsAggregationService.validate_range(payload.period_start, payload.period_end)
        definitions = self.db.scalars(select(AnalyticsMetricDefinition).where(
            AnalyticsMetricDefinition.enabled.is_(True),
            AnalyticsMetricDefinition.entity_type == payload.entity_type,
        ).limit(50)).all()
        seconds = int((payload.period_end - payload.period_start).total_seconds())
        buckets = sum((seconds + BUCKET_SECONDS[size] - 1) // BUCKET_SECONDS[size] for size in payload.bucket_sizes)
        estimated_entities = max(1, len(payload.entity_ids))
        if estimated_entities > payload.maximum_entities:
            raise HTTPException(413, "Backfill entity limit exceeded.")
        return {
            "metrics_affected": len(definitions), "entities_affected": estimated_entities,
            "estimated_buckets": buckets * estimated_entities * len(definitions),
            "existing_aggregates": self.db.query(AnalyticsAggregate).filter(
                AnalyticsAggregate.bucket_start >= payload.period_start,
                AnalyticsAggregate.bucket_end <= payload.period_end,
            ).count(),
            "estimated_duration_seconds": max(1, buckets * estimated_entities * len(definitions) // 100),
            "retention_conflicts": [], "warnings": ["Dry run does not persist aggregates."] if payload.dry_run else [],
        }

    def incremental_aggregate(self, run, bucket_size="5_minutes"):
        config = self.schedule()
        definitions = self.db.scalars(select(AnalyticsMetricDefinition).where(
            AnalyticsMetricDefinition.enabled.is_(True)
        ).limit(config.maximum_entities_per_run)).all()
        run.batches_total = len(definitions)
        for definition in definitions:
            if run.cancellation_requested:
                self.transition(run, "cancelled"); break
            checkpoint = self.db.scalar(select(AnalyticsCheckpoint).where(
                AnalyticsCheckpoint.metric_definition_id == definition.id,
                AnalyticsCheckpoint.entity_type == definition.entity_type,
                AnalyticsCheckpoint.entity_id.is_(None),
                AnalyticsCheckpoint.bucket_size == bucket_size,
                AnalyticsCheckpoint.calculation_type == "aggregate",
            ))
            start = run.period_start
            if checkpoint and checkpoint.completed_through:
                start = max(start, checkpoint.completed_through - timedelta(minutes=config.late_data_overlap_minutes))
            rows = AnalyticsAggregationService(self.db).aggregate(definition, None, start, run.period_end, bucket_size, True)
            if not checkpoint:
                checkpoint = AnalyticsCheckpoint(
                    metric_definition_id=definition.id, entity_type=definition.entity_type,
                    bucket_size=bucket_size, calculation_type="aggregate",
                )
                self.db.add(checkpoint)
            checkpoint.completed_through = run.period_end
            checkpoint.last_run_id = run.id
            run.aggregates_created += len(rows); run.records_created += len(rows)
            run.batches_completed += 1
            self.db.commit()
        return run

    def rollup(self, definition, entity_id, start, end, source_bucket, target_bucket):
        if BUCKET_SECONDS[target_bucket] <= BUCKET_SECONDS[source_bucket]:
            raise HTTPException(400, "Rollup target bucket must be larger than source bucket.")
        rows = self.db.scalars(select(AnalyticsAggregate).where(
            AnalyticsAggregate.metric_definition_id == definition.id,
            AnalyticsAggregate.entity_id == entity_id,
            AnalyticsAggregate.bucket_size == source_bucket,
            AnalyticsAggregate.bucket_start >= start,
            AnalyticsAggregate.bucket_end <= end,
        ).order_by(AnalyticsAggregate.bucket_start)).all()
        grouped = {}
        for row in rows:
            grouped.setdefault(AnalyticsAggregationService.bucket_start(row.bucket_start, target_bucket), []).append(row)
        output = []
        for bucket, values in grouped.items():
            count = sum(item.sample_count for item in values)
            weighted = sum((item.average_value or 0) * item.sample_count for item in values) / count if count else None
            output.append({
                "bucket_start": bucket, "bucket_end": bucket + timedelta(seconds=BUCKET_SECONDS[target_bucket]),
                "sample_count": count, "average_value": weighted,
                "minimum_value": min((v.minimum_value for v in values if v.minimum_value is not None), default=None),
                "maximum_value": max((v.maximum_value for v in values if v.maximum_value is not None), default=None),
                "sum_value": sum(v.sum_value or 0 for v in values), "latest_value": values[-1].latest_value,
                "quality": "good" if all(v.quality == "good" for v in values) else "partial",
            })
        return output

    def retention_preview(self):
        now = datetime.now(UTC); result = []
        policies = self.db.scalars(select(AnalyticsRetentionPolicy).where(AnalyticsRetentionPolicy.enabled.is_(True))).all()
        for policy in policies:
            cutoff = now - timedelta(days=policy.retention_days)
            count = 0
            if policy.record_type == "aggregate":
                query = self.db.query(AnalyticsAggregate).filter(AnalyticsAggregate.bucket_end < cutoff)
                if policy.bucket_size: query = query.filter(AnalyticsAggregate.bucket_size == policy.bucket_size)
                count = query.count()
            elif policy.record_type == "data_quality":
                count = self.db.query(AnalyticsDataQualityRecord).filter(AnalyticsDataQualityRecord.period_end < cutoff).count()
            elif policy.record_type == "run":
                count = self.db.query(AnalyticsRun).filter(AnalyticsRun.completed_at < cutoff).count()
            result.append({"policy_id": policy.id, "record_type": policy.record_type, "bucket_size": policy.bucket_size, "cutoff": cutoff, "eligible_records": count})
        return {"policies": result, "eligible_records": sum(item["eligible_records"] for item in result), "generated_at": now}

    def cleanup(self, batch_size=1000):
        preview = self.retention_preview(); deleted = 0; now = datetime.now(UTC)
        policies = self.db.scalars(select(AnalyticsRetentionPolicy).where(AnalyticsRetentionPolicy.enabled.is_(True))).all()
        for policy in policies:
            cutoff = now - timedelta(days=policy.retention_days)
            if policy.record_type == "aggregate":
                query = self.db.query(AnalyticsAggregate).filter(AnalyticsAggregate.bucket_end < cutoff)
                if policy.bucket_size: query = query.filter(AnalyticsAggregate.bucket_size == policy.bucket_size)
            elif policy.record_type == "data_quality":
                query = self.db.query(AnalyticsDataQualityRecord).filter(AnalyticsDataQualityRecord.period_end < cutoff)
            elif policy.record_type == "run":
                query = self.db.query(AnalyticsRun).filter(AnalyticsRun.completed_at < cutoff, AnalyticsRun.status.in_(("completed", "failed", "cancelled")))
            else:
                continue
            ids = [row[0] for row in query.with_entities(query.column_descriptions[0]["entity"].id).limit(batch_size).all()]
            if ids:
                deleted += query.filter(query.column_descriptions[0]["entity"].id.in_(ids)).delete(synchronize_session=False)
                self.db.commit()
        return {"deleted": deleted, "previewed": preview["eligible_records"], "completed_at": now}

    def trends(self, definition, entity_id, start, end, bucket_size, aggregation):
        field = {
            "average": AnalyticsAggregate.average_value, "minimum": AnalyticsAggregate.minimum_value,
            "maximum": AnalyticsAggregate.maximum_value, "sum": AnalyticsAggregate.sum_value,
            "latest": AnalyticsAggregate.latest_value, "percentile": AnalyticsAggregate.percentile_95,
        }.get(aggregation)
        if field is None: raise HTTPException(400, "Unsupported trend aggregation.")
        rows = self.db.query(AnalyticsAggregate.bucket_start, field, AnalyticsAggregate.quality).filter(
            AnalyticsAggregate.metric_definition_id == definition.id,
            AnalyticsAggregate.entity_id == entity_id,
            AnalyticsAggregate.bucket_size == bucket_size,
            AnalyticsAggregate.bucket_start >= start, AnalyticsAggregate.bucket_end <= end,
        ).order_by(AnalyticsAggregate.bucket_start).limit(settings.analytics_maximum_time_series_points + 1).all()
        if len(rows) > settings.analytics_maximum_time_series_points: raise HTTPException(413, "Trend result exceeds configured limit.")
        values = [float(value) for _, value, _ in rows if value is not None]
        return {
            "series": [{"timestamp": timestamp, "value": value, "quality": quality} for timestamp, value, quality in rows],
            "summary": {"minimum": min(values) if values else None, "maximum": max(values) if values else None, "average": sum(values) / len(values) if values else None, "sample_count": len(values)},
            "data_quality": {"good": sum(quality == "good" for _, _, quality in rows), "total": len(rows)},
            "unit": definition.unit,
        }

    def assess_data_quality(self, run, bucket_size="5_minutes"):
        definitions = self.db.scalars(select(AnalyticsMetricDefinition).where(AnalyticsMetricDefinition.enabled.is_(True)).limit(100)).all()
        interval = BUCKET_SECONDS[bucket_size]
        expected = max(1, int((run.period_end - run.period_start).total_seconds() / interval))
        created = 0
        for definition in definitions:
            rows = self.db.query(
                AnalyticsAggregate.entity_id, func.sum(AnalyticsAggregate.sample_count)
            ).filter(
                AnalyticsAggregate.metric_definition_id == definition.id,
                AnalyticsAggregate.bucket_start >= run.period_start,
                AnalyticsAggregate.bucket_end <= run.period_end,
            ).group_by(AnalyticsAggregate.entity_id).all()
            for entity_id, actual in rows:
                if entity_id is None: continue
                actual = int(actual or 0); coverage = min(100.0, actual / expected * 100)
                identity = dict(entity_type=definition.entity_type, entity_id=entity_id, metric_key=definition.metric_key, period_start=run.period_start, period_end=run.period_end)
                record = self.db.scalar(select(AnalyticsDataQualityRecord).filter_by(**identity))
                values = dict(expected_samples=expected, actual_samples=actual, coverage_percent=coverage, missing_samples=max(0, expected - actual), invalid_samples=0, stale_samples=0, quality_status="good" if coverage >= 90 else "partial" if coverage >= 50 else "poor", calculated_at=datetime.now(UTC))
                if record:
                    for key, value in values.items(): setattr(record, key, value)
                    run.records_updated += 1
                else:
                    self.db.add(AnalyticsDataQualityRecord(**identity, **values)); created += 1
        run.records_created += created; self.db.commit()
        return created

    def assess_capacity(self, run):
        policies = self.db.scalars(select(CapacityPolicy).where(CapacityPolicy.enabled.is_(True)).limit(100)).all()
        created = 0
        for policy in policies:
            definition = self.db.scalar(select(AnalyticsMetricDefinition).where(AnalyticsMetricDefinition.metric_key == policy.metric_key, AnalyticsMetricDefinition.enabled.is_(True)))
            if not definition: continue
            entities = self.db.scalars(select(AnalyticsAggregate.entity_id).where(
                AnalyticsAggregate.metric_definition_id == definition.id,
                AnalyticsAggregate.entity_id.is_not(None),
                AnalyticsAggregate.bucket_start >= run.period_start,
                AnalyticsAggregate.bucket_end <= run.period_end,
            ).distinct().limit(self.schedule().maximum_entities_per_run)).all()
            for entity_id in entities:
                rows = self.db.scalars(select(AnalyticsAggregate).where(
                    AnalyticsAggregate.metric_definition_id == definition.id,
                    AnalyticsAggregate.entity_id == entity_id,
                    AnalyticsAggregate.bucket_start >= run.period_start,
                    AnalyticsAggregate.bucket_end <= run.period_end,
                ).order_by(AnalyticsAggregate.bucket_start)).all()
                values = [row.average_value for row in rows if row.average_value is not None]
                result = AnalyticsCapacityService.assess(policy, values, max(1, int((run.period_end - run.period_start).total_seconds())))
                identity = dict(policy_id=policy.id, entity_type=policy.entity_type, entity_id=entity_id, period_start=run.period_start, period_end=run.period_end)
                record = self.db.scalar(select(CapacityAssessment).filter_by(**identity))
                payload = dict(metric_key=policy.metric_key, current_value=result.get("current_value"), average_value=result.get("average_value"), peak_value=result.get("peak_value"), percentile_95=result.get("percentile_95"), threshold_status=result["threshold_status"], threshold_breach_duration_seconds=result.get("threshold_breach_duration_seconds", 0), sample_count=result["sample_count"], data_quality=result["data_quality"], explanation=result.get("explanation", {}))
                if record:
                    for key, value in payload.items(): setattr(record, key, value)
                    run.records_updated += 1
                else:
                    self.db.add(CapacityAssessment(**identity, **payload)); created += 1
        run.capacity_assessments_created += created; run.records_created += created; self.db.commit()
        return created
