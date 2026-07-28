"""Bounded, explainable operational event correlation and insight templates."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.analytics import AnalyticsAnomaly, AnalyticsCorrelationGroup, AnalyticsCorrelationMember, AnalyticsInsight


class AnalyticsCorrelationService:
    def __init__(self, db):
        self.db = db

    def correlate(self, window_minutes: int = 15, maximum_events: int = 1000, maximum_groups: int = 100):
        window_minutes=max(1,min(window_minutes,1440)); maximum_events=max(1,min(maximum_events,5000)); maximum_groups=max(1,min(maximum_groups,500))
        cutoff=datetime.now(timezone.utc)-timedelta(minutes=window_minutes)
        anomalies=self.db.scalars(select(AnalyticsAnomaly).where(
            AnalyticsAnomaly.status.in_(("open","acknowledged")), AnalyticsAnomaly.last_detected_at>=cutoff
        ).order_by(AnalyticsAnomaly.last_detected_at).limit(maximum_events)).all()
        grouped={}
        for anomaly in anomalies: grouped.setdefault((anomaly.entity_type, anomaly.entity_id), []).append(anomaly)
        created=0
        for (entity_type,entity_id), members in list(grouped.items())[:maximum_groups]:
            if len(members)<2: continue
            existing=self.db.scalar(select(AnalyticsCorrelationGroup).where(
                AnalyticsCorrelationGroup.status.in_(("open","under_review","confirmed")),
                AnalyticsCorrelationGroup.probable_common_entity_type==entity_type,
                AnalyticsCorrelationGroup.probable_common_entity_id==entity_id,
                AnalyticsCorrelationGroup.correlation_type=="simultaneous_failure"))
            confidence=min(95.0,55+len(members)*5)
            if not existing:
                existing=AnalyticsCorrelationGroup(title=f"Probable shared {entity_type} event group",
                    description=f"{len(members)} unusual observations occurred within {window_minutes} minutes and share one {entity_type}. This is a probable relationship, not a confirmed root cause.",
                    severity=max((item.severity for item in members),key=lambda value:{"informational":0,"warning":1,"high":2,"critical":3}.get(value,0)),
                    correlation_type="simultaneous_failure",confidence_score=confidence,probable_common_entity_type=entity_type,
                    probable_common_entity_id=entity_id,first_event_at=min(item.first_detected_at for item in members),
                    last_event_at=max(item.last_detected_at for item in members),event_count=len(members),anomaly_count=len(members),
                    affected_device_count=1 if entity_type=="device" else 0,evidence={"window_minutes":window_minutes,"member_ids":[str(item.id) for item in members[:100]],"limitations":["Shared scope and timing do not prove causation."]})
                self.db.add(existing); self.db.flush(); created+=1
            else:
                existing.last_event_at=max(item.last_detected_at for item in members); existing.event_count=len(members); existing.anomaly_count=len(members); existing.confidence_score=confidence
            for anomaly in members:
                found=self.db.scalar(select(AnalyticsCorrelationMember.id).where(AnalyticsCorrelationMember.correlation_group_id==existing.id,AnalyticsCorrelationMember.anomaly_id==anomaly.id))
                if not found: self.db.add(AnalyticsCorrelationMember(correlation_group_id=existing.id,member_type="anomaly",anomaly_id=anomaly.id,
                    entity_type=anomaly.entity_type,entity_id=anomaly.entity_id,relationship_type="shared_scope_and_time",confidence_contribution=confidence/len(members),
                    evidence={"metric_key":anomaly.metric_key},occurred_at=anomaly.last_detected_at))
            self._insight(existing)
        self.db.flush()
        return {"events_evaluated":len(anomalies),"groups_created":created,"bounded":len(anomalies)>=maximum_events}

    def _insight(self, group):
        existing=self.db.scalar(select(AnalyticsInsight).where(AnalyticsInsight.correlation_group_id==group.id,AnalyticsInsight.status=="open"))
        if existing: return existing
        row=AnalyticsInsight(insight_type="probable_shared_dependency",entity_type=group.probable_common_entity_type or "system",
            entity_id=group.probable_common_entity_id,correlation_group_id=group.id,title="Review probable shared operational dependency",
            summary=f"{group.event_count} related events share timing and scope. Review the common entity before concluding cause.",
            severity=group.severity,confidence_score=group.confidence_score,evidence={"correlation_group_id":str(group.id),"correlation_type":group.correlation_type},
            recommended_review_steps=["Inspect the probable shared entity.","Review related alerts and open tickets.","Confirm maintenance activity.","Validate topology evidence."])
        self.db.add(row); return row
