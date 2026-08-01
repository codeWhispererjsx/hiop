"""Transactional internal-event outbox with bounded retry and retention."""
import json
import uuid
from datetime import datetime,timedelta,timezone

from app.models.automation_triggers import AutomationEventOutbox,AutomationEventRecord,AutomationTriggerCorrelationGroup
from app.services.automation_trigger_service import EVENT_CATALOG,process_event,validate_payload

MAX_ATTEMPTS=5

def publish_internal_event(db,*,event_type,property_id=None,source_entity_type=None,source_entity_id=None,safe_payload=None,severity=None,status=None,correlation_key=None):
    if event_type not in EVENT_CATALOG:raise ValueError("event type is not registered")
    payload=safe_payload or {};validate_payload(payload)
    envelope={"source_entity_type":source_entity_type,"source_entity_id":str(source_entity_id) if source_entity_id else None,"severity":severity,"status":status,"correlation_key":correlation_key,"safe_payload":payload}
    encoded=json.dumps(envelope,separators=(",",":"))
    if len(encoded)>10000:raise ValueError("event payload exceeds limit")
    row=AutomationEventOutbox(event_id=uuid.uuid4(),event_type=event_type,property_id=property_id,payload=encoded,status="pending",next_attempt_at=datetime.now(timezone.utc));db.add(row);db.flush();return row

def process_outbox_batch(db,limit=100):
    now=datetime.now(timezone.utc);published=failed=dead_letter=0
    db.query(AutomationTriggerCorrelationGroup).filter(AutomationTriggerCorrelationGroup.status=="collecting",AutomationTriggerCorrelationGroup.expires_at<=now).update({"status":"expired"},synchronize_session=False)
    rows=db.query(AutomationEventOutbox).filter(AutomationEventOutbox.status.in_(("pending","failed")),AutomationEventOutbox.next_attempt_at<=now).order_by(AutomationEventOutbox.created_at).limit(min(max(limit,1),100)).all()
    for row in rows:
        try:
            envelope=json.loads(row.payload);event=db.query(AutomationEventRecord).filter_by(event_id=row.event_id).first()
            if not event:
                source_id=envelope.get("source_entity_id")
                event=AutomationEventRecord(event_id=row.event_id,event_type=row.event_type,property_id=row.property_id,source_module=EVENT_CATALOG[row.event_type]["module"],source_entity_type=envelope.get("source_entity_type"),source_entity_id=uuid.UUID(source_id) if source_id else None,severity=envelope.get("severity"),status=envelope.get("status"),correlation_key=envelope.get("correlation_key"),safe_payload=json.dumps(envelope.get("safe_payload") or {},separators=(",",":")),occurred_at=now);db.add(event);db.flush()
            process_event(db,event)
            from app.services.incident_event_service import create_pending_incident_from_event
            create_pending_incident_from_event(db,event)
            row.status="published";row.published_at=now;row.error_summary=None;published+=1
        except Exception:
            row.attempts+=1;row.error_summary="Internal event processing failed"
            if row.attempts>=MAX_ATTEMPTS:row.status="dead_letter";row.next_attempt_at=None;dead_letter+=1
            else:row.status="failed";row.next_attempt_at=now+timedelta(seconds=min(300,2**row.attempts));failed+=1
    db.commit();return {"processed":len(rows),"published":published,"failed":failed,"dead_letter":dead_letter}

def retry_dead_letter(db,row):
    row.status="pending";row.attempts=0;row.error_summary=None;row.next_attempt_at=datetime.now(timezone.utc);db.commit();return row

def retention_preview(db,days=30):
    cutoff=datetime.now(timezone.utc)-timedelta(days=min(max(days,7),365))
    events=db.query(AutomationEventRecord).filter(AutomationEventRecord.received_at<cutoff,AutomationEventRecord.processing_status.in_(("unmatched","suppressed","triggered"))).count()
    outbox=db.query(AutomationEventOutbox).filter(AutomationEventOutbox.created_at<cutoff,AutomationEventOutbox.status=="published").count()
    return {"cutoff":cutoff,"eligible_events":events,"eligible_outbox":outbox,"protected_dead_letters":db.query(AutomationEventOutbox).filter_by(status="dead_letter").count()}

def cleanup_retention(db,days=30,batch_size=500):
    preview=retention_preview(db,days);cutoff=preview["cutoff"];limit=min(max(batch_size,1),1000)
    outbox=db.query(AutomationEventOutbox).filter(AutomationEventOutbox.created_at<cutoff,AutomationEventOutbox.status=="published").limit(limit).all()
    for row in outbox:db.delete(row)
    # Event rows with trigger executions are FK protected and intentionally retained.
    db.commit();return {"deleted_outbox":len(outbox),"deleted_events":0,"protected_dead_letters":preview["protected_dead_letters"]}
