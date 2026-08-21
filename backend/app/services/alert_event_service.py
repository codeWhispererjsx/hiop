"""V3E event-to-alert evaluation over persisted V3D observations."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.alert import Alert, AlertHistory, AlertRule, InAppNotification, MonitoringEvent
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.port_intelligence import PortDeviceAssociation
from app.models.user import User
from app.models.hierarchy import Property
from app.models.property_access import UserPropertyAccess
from app.services.monitoring_health_service import device_health
from app.services.settings_service import _all, _group

def offline_breached(scans,required):return len(scans)>=required and all(row.status.lower()=="offline" for row in scans[:required])
def latency_breached(scans,required,threshold):return len(scans)>=required and all(row.response_time is not None and row.response_time>threshold for row in scans[:required])
def failed_check_percent(scans):return None if len(scans)<2 else sum(row.status.lower()=="offline" for row in scans)*100/len(scans)

def _active(db,device_id,kind):return db.query(Alert).filter(Alert.device_id==device_id,Alert.alert_type==kind,Alert.lifecycle_status.in_(("open","acknowledged"))).first()
def _history(db,alert,action,actor,previous,current,reason):db.add(AlertHistory(alert_id=alert.id,action=action,actor=actor,previous_status=previous,current_status=current,reason=reason))

def _notify(db:Session,alert:Alert,rule:AlertRule):
    if rule.notify_in_app:
        query=db.query(User).filter(User.is_active.is_(True),User.organization_id==rule.organization_id) if rule.organization_id else db.query(User).filter(User.is_active.is_(True))
        if rule.property_id:
            query=query.join(UserPropertyAccess,UserPropertyAccess.user_id==User.id).filter(UserPropertyAccess.property_id==rule.property_id,UserPropertyAccess.enabled.is_(True))
        for user in query.all():db.add(InAppNotification(alert_id=alert.id,user_id=user.id,delivery_status="delivered"))
    if rule.notify_email:
        config=_group(_all(db),"notifications");recipient=config.get("recipient_email")
        note=InAppNotification(alert_id=alert.id,user_id=None,channel="email",delivery_status="pending");db.add(note)
        if not config.get("email_notifications") or not recipient:note.delivery_status="suppressed";note.error_summary="Email notification or recipient is not configured";return
        try:
            from app.services.email_service import send_email
            send_email(f"[{alert.severity.upper()}] {alert.title}",f"{alert.reason}\nEvidence: {alert.evidence}",recipient);note.delivery_status="delivered"
        except Exception as exc:note.delivery_status="failed";note.error_summary=str(exc)[:500]

def _open(db,device,rule,kind,title,reason,evidence,value=None):
    existing=_active(db,device.id,kind)
    if existing:existing.last_updated_at=datetime.now(timezone.utc);existing.current_value=value;existing.evidence=evidence;return existing,False
    alert=Alert(device_id=device.id,previous_status=device.network_status or "Unknown",current_status=device.network_status or "Unknown",message=title,rule_id=rule.id,alert_type=kind,title=title,severity=rule.severity,lifecycle_status="open",source="V3D monitoring",reason=reason,evidence=evidence,current_value=value,threshold_value=rule.threshold_value,deduplication_key=f"{device.id}:{kind}");db.add(alert);db.flush();_history(db,alert,"opened","system",None,"open",reason);_notify(db,alert,rule);return alert,True

def _resolve(db,device_id,kind,reason):
    alert=_active(db,device_id,kind)
    if not alert:return False
    previous=alert.lifecycle_status;alert.lifecycle_status="resolved";alert.resolved_at=datetime.now(timezone.utc);alert.resolution_reason=reason;alert.last_updated_at=alert.resolved_at;_history(db,alert,"auto_resolved","system",previous,"resolved",reason);return True

def evaluate_scan(db:Session,device:Device,scan:NetworkScan):
    event_type="device_reachable" if scan.status.lower()=="online" else "device_unreachable"
    existing_event=db.query(MonitoringEvent).filter_by(source_type="network_scan",source_id=str(scan.id),event_type=event_type).first()
    if existing_event:return {"event":existing_event,"opened":0,"resolved":0,"duplicate_prevented":True}
    event=MonitoringEvent(device_id=device.id,event_type=event_type,source="ICMP",source_type="network_scan",source_id=str(scan.id),value_numeric=scan.response_time,evidence={"status":scan.status,"latency_ms":scan.response_time},occurred_at=scan.scanned_at or datetime.now(timezone.utc));db.add(event)
    prop=db.get(Property,device.property_id) if device.property_id else None;organization_id=prop.organization_id if prop else None
    available=db.query(AlertRule).filter(AlertRule.enabled.is_(True),((AlertRule.organization_id==organization_id)|(AlertRule.organization_id.is_(None)))).all()
    rules={row.rule_type:row for row in available if row.organization_id is None}
    for row in available:
        if row.organization_id==organization_id and row.property_id is None:rules[row.rule_type]=row
        if device.property_id and row.organization_id==organization_id and row.property_id==device.property_id:rules[row.rule_type]=row
    recent=db.query(NetworkScan).filter(NetworkScan.device_id==device.id).order_by(NetworkScan.scanned_at.desc()).limit(20).all();opened=resolved=0
    offline=rules.get("device_offline")
    if offline:
        required=1 if any(word in device.device_type.lower() for word in ("switch","router","firewall")) else offline.consecutive_observations
        if offline_breached(recent,required):
            context=db.query(PortDeviceAssociation).filter(PortDeviceAssociation.switch_device_id==device.id,PortDeviceAssociation.is_current.is_(True)).count()
            _,created=_open(db,device,offline,"device_offline",f"{device.hostname} unavailable",f"{required} consecutive failed checks",{"failed_checks":required,"potentially_affected_devices":context,"causation_claimed":False});opened+=created
        elif scan.status.lower()=="online":resolved+=_resolve(db,device.id,"device_offline","Device became reachable")
    latency_rule=rules.get("high_latency")
    if latency_rule:
        required=latency_rule.consecutive_observations;points=recent[:required]
        if latency_breached(points,required,latency_rule.threshold_value):
            average=sum(row.response_time for row in points)/required;_,created=_open(db,device,latency_rule,"high_latency",f"{device.hostname} sustained high latency",f"{required} consecutive checks exceeded {latency_rule.threshold_value} ms",{"observations":required,"average_latency_ms":average},average);opened+=created
        elif scan.response_time is not None and scan.response_time<=latency_rule.threshold_value:resolved+=_resolve(db,device.id,"high_latency","Latency returned below threshold")
    loss_rule=rules.get("packet_loss")
    if loss_rule:
        sample=recent[:loss_rule.consecutive_observations]
        loss=failed_check_percent(sample)
        if loss is not None and loss>loss_rule.threshold_value:
            _,created=_open(db,device,loss_rule,"packet_loss",f"{device.hostname} packet loss elevated",f"Failed-check rate {loss:.1f}% exceeds {loss_rule.threshold_value}%",{"failed":sum(row.status.lower()=="offline" for row in sample),"probes":len(sample)},loss);opened+=created
        elif loss is not None and loss<=loss_rule.threshold_value:resolved+=_resolve(db,device.id,"packet_loss","Failed-check rate returned below threshold")
    health_rule=rules.get("health_degradation");health=device_health(db,device,"1h")
    if health_rule and health["health"] in {"Degraded","Unhealthy"} and len(recent)>=health_rule.consecutive_observations:
        _,created=_open(db,device,health_rule,"health_degradation",f"{device.hostname} health is {health['health']}","; ".join(health["reasons"]),{"health":health["health"],"confidence":health["confidence"]});opened+=created
    elif health_rule and health["health"]=="Healthy":resolved+=_resolve(db,device.id,"health_degradation","Device health returned to Healthy")
    event.processed_at=datetime.now(timezone.utc);return {"event":event,"opened":opened,"resolved":resolved,"duplicate_prevented":False}
