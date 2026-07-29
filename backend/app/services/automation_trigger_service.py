"""Bounded matching and execution for trusted internal HIOP events."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.automation import AutomationApprovalRequest, AutomationWorkflow, AutomationWorkflowRun, AutomationWorkflowVersion
from app.models.automation_triggers import AutomationEventRecord, AutomationTriggerExecution, AutomationTriggerSubscription
from app.services.workflow_condition_service import evaluate
from app.websocket.connection_manager import manager

EVENT_CATALOG={
    "alert_created":{"module":"alerts","fields":{"severity","status","source_entity_id","property_id"}},
    "alert_acknowledged":{"module":"alerts","fields":{"severity","status","source_entity_id","property_id"}},
    "alert_escalated":{"module":"alerts","fields":{"severity","status","source_entity_id","property_id"}},
    "alert_resolved":{"module":"alerts","fields":{"severity","status","source_entity_id","property_id"}},
    "critical_alert_created":{"module":"alerts","fields":{"severity","status","source_entity_id","property_id"}},
    "repeated_alert_detected":{"module":"alerts","fields":{"severity","status","source_entity_id","property_id","occurrence_count"}},
    "ticket_created":{"module":"tickets","fields":{"severity","status","source_entity_id","property_id"}},
    "ticket_assigned":{"module":"tickets","fields":{"severity","status","source_entity_id","property_id"}},
    "ticket_priority_changed":{"module":"tickets","fields":{"severity","status","source_entity_id","property_id"}},
    "ticket_status_changed":{"module":"tickets","fields":{"status","source_entity_id","property_id"}},
    "ticket_overdue":{"module":"tickets","fields":{"severity","status","source_entity_id","property_id"}},
    "ticket_resolved":{"module":"tickets","fields":{"status","source_entity_id","property_id"}},
    "ticket_reopened":{"module":"tickets","fields":{"severity","status","source_entity_id","property_id"}},
    "device_created":{"module":"devices","fields":{"status","source_entity_id","property_id","device_type"}},
    "device_status_changed":{"module":"devices","fields":{"status","source_entity_id","property_id","device_type"}},
    "device_offline":{"module":"devices","fields":{"status","source_entity_id","property_id"}},
    "device_restored":{"module":"devices","fields":{"status","source_entity_id","property_id"}},
    "device_retired":{"module":"devices","fields":{"status","source_entity_id","property_id"}},
    "device_classification_changed":{"module":"devices","fields":{"status","source_entity_id","property_id","device_type"}},
    "device_requires_review":{"module":"devices","fields":{"status","source_entity_id","property_id"}},
    "discovery_completed":{"module":"discovery","fields":{"status","property_id","occurrence_count"}},
    "new_device_discovered":{"module":"discovery","fields":{"status","source_entity_id","property_id","device_type"}},
    "discovery_candidate_approved":{"module":"discovery","fields":{"status","source_entity_id","property_id"}},
    "discovery_failed":{"module":"discovery","fields":{"status","property_id"}},
    "directory_sync_completed":{"module":"active_directory","fields":{"status","property_id","occurrence_count"}},
    "directory_sync_failed":{"module":"active_directory","fields":{"status","property_id"}},
    "directory_object_changed":{"module":"active_directory","fields":{"status","source_entity_id","property_id"}},
    "directory_candidate_detected":{"module":"active_directory","fields":{"status","source_entity_id","property_id"}},
    "SNMP_target_unreachable":{"module":"snmp","fields":{"severity","source_entity_id","property_id"}},
    "SNMP_target_restored":{"module":"snmp","fields":{"status","source_entity_id","property_id"}},
    "SNMP_interface_down":{"module":"snmp","fields":{"severity","source_entity_id","property_id"}},
    "SNMP_interface_restored":{"module":"snmp","fields":{"status","source_entity_id","property_id"}},
    "SNMP_threshold_breached":{"module":"snmp","fields":{"severity","source_entity_id","property_id"}},
    "SNMP_poll_failed":{"module":"snmp","fields":{"severity","source_entity_id","property_id"}},
    "topology_link_missing":{"module":"topology","fields":{"severity","source_entity_id","property_id"}},
    "topology_link_restored":{"module":"topology","fields":{"status","source_entity_id","property_id"}},
    "topology_partition_detected":{"module":"topology","fields":{"severity","source_entity_id","property_id"}},
    "topology_conflict_created":{"module":"topology","fields":{"severity","source_entity_id","property_id"}},
    "topology_change_detected":{"module":"topology","fields":{"severity","source_entity_id","property_id"}},
    "analytics_anomaly_detected":{"module":"analytics","fields":{"severity","source_entity_id","property_id"}},
    "analytics_anomaly_resolved":{"module":"analytics","fields":{"status","source_entity_id","property_id"}},
    "capacity_warning_created":{"module":"analytics","fields":{"severity","source_entity_id","property_id"}},
    "SLA_breach_detected":{"module":"analytics","fields":{"severity","source_entity_id","property_id"}},
    "health_score_degraded":{"module":"analytics","fields":{"severity","source_entity_id","property_id"}},
    "correlation_group_created":{"module":"analytics","fields":{"severity","source_entity_id","property_id","occurrence_count"}},
    "technology_service_degraded":{"module":"hospitality","fields":{"severity","source_entity_id","property_id"}},
    "technology_service_unavailable":{"module":"hospitality","fields":{"severity","source_entity_id","property_id"}},
    "technology_service_restored":{"module":"hospitality","fields":{"status","source_entity_id","property_id"}},
    "property_operational_status_changed":{"module":"hospitality","fields":{"status","property_id"}},
    "guest_impact_detected":{"module":"hospitality","fields":{"severity","source_entity_id","property_id"}},
    "revenue_impact_detected":{"module":"hospitality","fields":{"severity","source_entity_id","property_id"}},
    "security_service_degraded":{"module":"hospitality","fields":{"severity","source_entity_id","property_id"}},
    "configuration_backup_failed":{"module":"configuration","fields":{"severity","source_entity_id","property_id"}},
    "configuration_drift_detected":{"module":"configuration","fields":{"severity","source_entity_id","property_id"}},
    "compliance_violation_created":{"module":"configuration","fields":{"severity","source_entity_id","property_id"}},
    "compliance_violation_resolved":{"module":"configuration","fields":{"status","source_entity_id","property_id"}},
    "change_request_approved":{"module":"configuration","fields":{"status","source_entity_id","property_id"}},
    "restore_validation_failed":{"module":"configuration","fields":{"severity","source_entity_id","property_id"}},
    "host_key_changed":{"module":"configuration","fields":{"severity","source_entity_id","property_id"}},
    "maintenance_window_started":{"module":"maintenance","fields":{"status","property_id"}},
    "maintenance_window_ending":{"module":"maintenance","fields":{"status","property_id"}},
    "maintenance_window_ended":{"module":"maintenance","fields":{"status","property_id"}},
    "report_completed":{"module":"reports","fields":{"status","source_entity_id","property_id"}},
    "report_failed":{"module":"reports","fields":{"status","source_entity_id","property_id"}},
}
SECRET_KEYS={"password","secret","token","community","credential","private_key","auth_secret","privacy_secret"}

def validate_payload(value,depth=0):
    if depth>4: raise ValueError("event payload nesting exceeds safe limit")
    if isinstance(value,dict):
        for key,item in value.items():
            if str(key).lower() in SECRET_KEYS: raise ValueError("event payload contains a prohibited field")
            validate_payload(item,depth+1)
    elif isinstance(value,list):
        if len(value)>100: raise ValueError("event payload array exceeds safe limit")
        for item in value: validate_payload(item,depth+1)
    elif not isinstance(value,(str,int,float,bool,type(None))): raise ValueError("event payload contains an unsupported value")

def validate_subscription(payload):
    errors=[];catalog=EVENT_CATALOG.get(payload.event_type)
    if not catalog: errors.append("Event type is not registered")
    filters=payload.filter_definition or {}
    if filters:
        def collect_fields(node):
            if not isinstance(node,dict): return set()
            fields={node.get("field")} if node.get("field") else set()
            for key in ("all","any"):
                for child in node.get(key,[]): fields.update(collect_fields(child))
            if "not" in node: fields.update(collect_fields(node["not"]))
            return fields
        fields=collect_fields(filters)
        invalid={field for field in fields if field and catalog and field not in catalog["fields"]}
        if invalid: errors.append(f"Filter fields are not allowed: {', '.join(sorted(invalid))}")
    if payload.maximum_runs_per_window<1 or payload.maximum_runs_per_window>100: errors.append("Run limit is outside safe bounds")
    if payload.delay_seconds>3600: errors.append("Delay exceeds safe limit")
    if payload.trigger_mode not in {"notify_only","execute","request_approval","create_pending_run"}: errors.append("Trigger mode is not supported")
    if payload.approval_mode not in {"use_workflow_policy","always_require"}: errors.append("Approval mode is not supported")
    if payload.maintenance_behavior not in {"suppress","allow"} or payload.blackout_behavior not in {"suppress","allow"}: errors.append("Window behavior is not supported")
    if payload.blackout_start and payload.blackout_end and payload.blackout_end<=payload.blackout_start: errors.append("Blackout end must be after blackout start")
    for target,path in (payload.input_mapping or {}).items():
        payload_field=path.split(".",1)[1] if isinstance(path,str) and path.startswith("safe_payload.") else None
        if not isinstance(target,str) or not isinstance(path,str) or len(target)>120 or not (path in {"property_id","source_entity_id","severity","status"} or (payload_field and catalog and payload_field in catalog["fields"])):
            errors.append("Input mapping contains an unsupported path");break
    return errors

def _maintenance_active(db,property_id):
    if not property_id:return False
    latest=db.query(AutomationEventRecord).filter(AutomationEventRecord.property_id==property_id,AutomationEventRecord.event_type.in_(("maintenance_window_started","maintenance_window_ended"))).order_by(AutomationEventRecord.occurred_at.desc()).first()
    return bool(latest and latest.event_type=="maintenance_window_started")

def _mapped_inputs(sub,event,payload):
    result={}
    for target,path in json.loads(sub.input_mapping or "{}").items():
        if path=="property_id":value=str(event.property_id) if event.property_id else None
        elif path=="source_entity_id":value=str(event.source_entity_id) if event.source_entity_id else None
        elif path in {"severity","status"}:value=getattr(event,path)
        else:value=payload.get(path.split(".",1)[1])
        result[target]=value
    return result

def preview_subscription(sub,event):
    payload=event.safe_payload if isinstance(event.safe_payload,dict) else json.loads(event.safe_payload or "{}")
    context={"severity":event.severity,"status":event.status,"source_entity_id":str(event.source_entity_id) if event.source_entity_id else None,"property_id":str(event.property_id) if event.property_id else None,**{k:v for k,v in payload.items() if isinstance(v,(str,int,float,bool,type(None)))}}
    filter_result=evaluate(json.loads(sub.filter_definition),context) if sub.filter_definition else {"result":True}
    condition_result=evaluate(json.loads(sub.condition_definition),context) if sub.condition_definition else {"result":True}
    return {"matched":bool(filter_result["result"] and condition_result["result"]),"filter_result":filter_result,"condition_result":condition_result,"mapped_inputs":_mapped_inputs(sub,event,payload),"would_execute":sub.enabled and sub.trigger_mode!="notify_only"}

def process_event(db,event,subscription_ids=None,bypass_deduplication=False):
    now=datetime.now(timezone.utc);payload=json.loads(event.safe_payload or "{}")
    context={"severity":event.severity,"status":event.status,"source_entity_id":str(event.source_entity_id) if event.source_entity_id else None,"property_id":str(event.property_id) if event.property_id else None,**{k:v for k,v in payload.items() if isinstance(v,(str,int,float,bool,type(None)))}}
    subscriptions=db.query(AutomationTriggerSubscription).filter_by(event_type=event.event_type,enabled=True).all();matched=triggered=suppressed=0
    for sub in subscriptions:
        if subscription_ids is not None and sub.id not in subscription_ids:continue
        if sub.property_id and sub.property_id!=event.property_id: continue
        matched+=1;dedupe=hashlib.sha256(f"{sub.id}:{event.correlation_key or event.source_entity_id or event.event_id}".encode()).hexdigest()
        cutoff=now-timedelta(seconds=max(sub.deduplication_window_seconds,sub.cooldown_seconds,sub.correlation_window_seconds))
        recent=db.query(AutomationTriggerExecution).filter(AutomationTriggerExecution.subscription_id==sub.id,AutomationTriggerExecution.deduplication_key==dedupe,AutomationTriggerExecution.created_at>=cutoff).first()
        window=now-timedelta(seconds=sub.run_window_seconds);count=db.query(AutomationTriggerExecution).filter(AutomationTriggerExecution.subscription_id==sub.id,AutomationTriggerExecution.status=="triggered",AutomationTriggerExecution.created_at>=window).count()
        reason=None
        if recent and not bypass_deduplication: reason="deduplicated"
        elif count>=sub.maximum_runs_per_window: reason="storm_protection"
        elif sub.blackout_behavior=="suppress" and sub.blackout_start and sub.blackout_end and sub.blackout_start<=now<=sub.blackout_end: reason="blackout_window"
        elif sub.maintenance_behavior=="suppress" and event.event_type not in {"maintenance_window_started","maintenance_window_ended"} and _maintenance_active(db,event.property_id): reason="maintenance_window"
        elif sub.filter_definition and not evaluate(json.loads(sub.filter_definition),context)["result"]: reason="filter_not_matched"
        elif sub.condition_definition and not evaluate(json.loads(sub.condition_definition),context)["result"]: reason="condition_not_matched"
        execution=AutomationTriggerExecution(subscription_id=sub.id,event_id=event.id,property_id=event.property_id,deduplication_key=dedupe,status="suppressed" if reason else "matched",suppression_reason=reason);db.add(execution)
        if reason: suppressed+=1;continue
        workflow=db.get(AutomationWorkflow,sub.workflow_id);version=db.get(AutomationWorkflowVersion,sub.workflow_version_id)
        if not workflow or not version or not workflow.enabled or version.status!="approved": execution.status="suppressed";execution.suppression_reason="workflow_not_active";suppressed+=1;continue
        if sub.trigger_mode=="notify_only": execution.status="notified";continue
        mapped_inputs=_mapped_inputs(sub,event,payload)
        if sub.delay_seconds and sub.trigger_mode not in {"request_approval","create_pending_run"} and sub.approval_mode!="always_require":
            from app.services.scheduler_service import scheduler,delayed_automation_event,AUTOMATION_DELAY_JOB_PREFIX
            db.flush();scheduler.add_job(delayed_automation_event,"date",run_date=now+timedelta(seconds=sub.delay_seconds),args=[str(workflow.id),str(event.event_id),str(sub.id),str(execution.id)],id=f"{AUTOMATION_DELAY_JOB_PREFIX}{execution.id}",replace_existing=True,max_instances=1,misfire_grace_time=300);execution.status="delayed";triggered+=1;continue
        if sub.trigger_mode in {"request_approval","create_pending_run"} or sub.approval_mode=="always_require":
            run=AutomationWorkflowRun(property_id=event.property_id,workflow_id=workflow.id,workflow_version_id=version.id,status="waiting_approval",trigger_type="internal_event",triggered_by="automation:event",idempotency_key=f"event:{event.event_id}:{sub.id}",error_summary=json.dumps({"mapped_inputs":mapped_inputs},separators=(",",":")));db.add(run);db.flush();db.add(AutomationApprovalRequest(workflow_run_id=run.id,requested_by="automation:event"));execution.status="triggered";triggered+=1
        else:
            from app.api.v1.automation import RunWrite,run_workflow
            result=run_workflow(workflow.id,RunWrite(idempotency_key=f"event:{event.event_id}:{sub.id}",dry_run=False),db,SimpleNamespace(id=None,username="automation:event",role="admin"));created=db.get(AutomationWorkflowRun,result["run_id"]);created.trigger_type="internal_event";created.error_summary=json.dumps({"mapped_inputs":mapped_inputs,"execution":result.get("result",{})},separators=(",",":"));execution.status="triggered";triggered+=1
    event.processing_status="triggered" if triggered else "suppressed" if suppressed else "unmatched";event.processed_at=now
    manager.broadcast_from_thread({"type":"automation_event_processed","event_id":str(event.event_id),"matched":matched,"triggered":triggered,"suppressed":suppressed})
    return {"matched":matched,"triggered":triggered,"suppressed":suppressed}
