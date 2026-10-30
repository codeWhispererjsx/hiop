import json
import logging
import shutil
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.core.security import get_db
from app.core.tenant import organization_context
from app.models.hierarchy import Organization
from app.core.security import get_current_user, require_roles
from app.models.alert import Alert
from app.models.device import Device
from app.models.hierarchy import Property
from app.models.network_scan import NetworkScan
from app.models.system_health import NotificationDelivery
from app.models.system_health import JobExecution
from app.models.backup import BackupRecord, RestoreTest
from app.models.discovery_intelligence import DiscoveryJob
from app.models.user import User
from app.schemas.settings import DiscoverySettings, GeneralSettings, IncidentSettings, NamingConventionSettings, NetworkSettings, NotificationSettings, OrganizationSettings, PublicSettings, SettingsBundle, SystemHealth
from app.services.audit_service import create_audit_log
from app.services import settings_service
from app.services.scheduler_service import AUTOMATION_OUTBOX_JOB_ID, DAILY_AUDIT_EMAIL_JOB_ID, configure_discovery_scheduler, configure_scheduler, network_scan_job_id, scheduler
from app.core.config import settings as app_settings

router = APIRouter(tags=["Operations"])
logger = logging.getLogger(__name__)
@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_roles(["admin", "technician"]))):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    create_audit_log(db, current_user.username, "ACKNOWLEDGE_ALERT", "Alert", str(alert.id), alert.message)
    db.commit()
    return {"id": str(alert.id), "acknowledged": True}


def user_bundle(db, user):
    if user.organization_id: db.info["organization_id"]=user.organization_id
    result=settings_service.read_bundle(db)
    organization=db.get(Organization,user.organization_id) if user.organization_id else None
    if organization:
        result["general"]["timezone"]=organization.timezone
        result["organization"]["organization_name"]=organization.name
    return result

@router.get("/settings", response_model=SettingsBundle)
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    return user_bundle(db, _)


@router.get("/settings/public", response_model=PublicSettings)
def public_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if _.organization_id: db.info["organization_id"]=_.organization_id
    result=settings_service.read_public(db)
    organization=db.get(Organization,_.organization_id) if _.organization_id else None
    if organization:
        result.update(timezone=organization.timezone,organization_name=organization.name,logo=organization.logo)
    return result


def save_settings_group(db: Session, user: User, group: str, payload):
    if user.organization_id: db.info["organization_id"]=user.organization_id
    try:
        settings_service.save_group(db, group, payload)
        create_audit_log(db, user.username, f"UPDATE_{group.upper()}_SETTINGS", "Settings", group, f"Updated {group} settings")
        db.commit()
    except Exception:
        db.rollback(); raise
    return user_bundle(db, user)


@router.put("/settings/general", response_model=SettingsBundle)
def update_general(payload: GeneralSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"])), org=Depends(organization_context)):
    organization=db.get(Organization,org)
    organization.timezone=payload.timezone
    return save_settings_group(db, user, "general", payload)


@router.put("/settings/organization", response_model=SettingsBundle)
def update_organization(payload: OrganizationSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    organization=db.get(Organization,user.organization_id) if user.organization_id else None
    if organization:
        organization.name=payload.organization_name
        organization.address=payload.address
        organization.contact_email=str(payload.support_email) if payload.support_email else None
        organization.contact_phone=payload.support_phone
    return save_settings_group(db, user, "organization", payload)


@router.put("/settings/network", response_model=SettingsBundle)
def update_network(payload: NetworkSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    result = save_settings_group(db, user, "network", payload)
    configure_scheduler(payload.automatic_scanning, payload.scan_interval_minutes,user.organization_id)
    return result


@router.put("/settings/notifications", response_model=SettingsBundle)
def update_notifications(payload: NotificationSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "notifications", payload)


@router.put("/settings/discovery", response_model=SettingsBundle)
def update_discovery(payload: DiscoverySettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    result = save_settings_group(db, user, "discovery", payload)
    if not user.organization_id: configure_discovery_scheduler(payload.enabled, payload.interval_minutes)
    return result


@router.put("/settings/incidents", response_model=SettingsBundle)
def update_incidents(payload: IncidentSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "incidents", payload)


@router.put("/settings/naming-convention", response_model=SettingsBundle)
def update_naming_convention(payload: NamingConventionSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    if not user.organization_id:
        raise HTTPException(403, "Organization context is required to configure asset naming.")
    db.info["organization_id"] = user.organization_id
    try:
        settings_service.save_naming_convention(db, payload)
        create_audit_log(db, user.username, "UPDATE_NAMING_CONVENTION", "Settings", "naming_convention", "Updated asset naming convention")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return user_bundle(db, user)


@router.get("/settings/system-health")
def system_health(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    result=settings_service.health(db)
    return {"status":result["status"],"email":result["email"]}


@router.get("/settings/automation-status")
def automation_status(db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    bundle=user_bundle(db,user)
    network=bundle["network"]
    notifications=bundle["notifications"]
    email_configured=bool(bundle["email"].get("configured") and notifications.get("recipient_email"))
    organization_id=user.organization_id

    def latest_delivery(notification_type):
        query=db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_type==notification_type,
            NotificationDelivery.organization_id==organization_id if organization_id else NotificationDelivery.organization_id.is_(None),
        ).order_by(NotificationDelivery.attempted_at.desc())
        return query.first()

    def last_successful_delivery(notification_type):
        query=db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_type==notification_type,
            NotificationDelivery.organization_id==organization_id if organization_id else NotificationDelivery.organization_id.is_(None),
            NotificationDelivery.status=="sent",
        ).order_by(NotificationDelivery.delivered_at.desc())
        return query.first()

    def delivery_details(row, successful_row):
        return {
            "last_attempt":row.attempted_at.isoformat() if row and row.attempted_at else None,
            "last_success":successful_row.delivered_at.isoformat() if successful_row and successful_row.delivered_at else None,
            "last_error":row.error if row and row.status.casefold()!="sent" else None,
            "delivery_status":row.status.casefold() if row else "not_run",
        }

    email_delivery=latest_delivery("email")
    email_success=last_successful_delivery("email")
    email_state=("disabled" if not notifications["email_notifications"] else
                 "not_configured" if not email_configured else
                 "failed" if email_delivery and email_delivery.status.casefold()!="sent" else "enabled")
    email_status={
        "state":email_state,
        "enabled":notifications["email_notifications"],
        "details":("Configure SMTP and a recipient before enabling email." if email_state=="not_configured" else
                   "The most recent email delivery failed." if email_state=="failed" else
                   "Email notifications are enabled; delivery is verified when an email is sent." if email_state=="enabled" else
                   "Email notifications are turned off."),
        **delivery_details(email_delivery,email_success),
    }

    audit_delivery=latest_delivery("daily_audit")
    audit_success=last_successful_delivery("daily_audit")
    audit_configured=email_configured and bool(app_settings.scheduler_enabled)
    audit_state=("disabled" if not notifications["daily_audit_email"] else
                 "not_configured" if not audit_configured else
                 "failed" if audit_delivery and audit_delivery.status.casefold()!="sent" else
                 "running" if scheduler.running and scheduler.get_job(DAILY_AUDIT_EMAIL_JOB_ID) else "enabled")
    audit_status={
        "state":audit_state,
        "enabled":notifications["daily_audit_email"],
        "details":("Configure SMTP, a recipient, and the scheduler before enabling daily audit email." if audit_state=="not_configured" else
                   "The most recent audit email delivery failed." if audit_state=="failed" else
                   "The daily delivery job is scheduled." if audit_state=="running" else
                   "Daily audit email is enabled but its scheduler is not currently running." if audit_state=="enabled" else
                   "Daily audit email is turned off."),
        **delivery_details(audit_delivery,audit_success),
    }

    offline_enabled=network["automatic_offline_tickets"]
    network_job_id=network_scan_job_id(user.organization_id)
    offline_job_running=(
        scheduler.running
        and bool(scheduler.get_job(network_job_id))
        and bool(scheduler.get_job(AUTOMATION_OUTBOX_JOB_ID))
    )
    offline_state=("disabled" if not offline_enabled else
                   "not_configured" if not network["automatic_scanning"] or not app_settings.scheduler_enabled else
                   "running" if offline_job_running else "enabled")
    offline_status={
        "state":offline_state,
        "enabled":offline_enabled,
        "details":("Enable scheduled network scans and the scheduler to detect offline devices automatically." if offline_state=="not_configured" else
                   "Repeated monitoring failures are checked and offline incidents are processed automatically." if offline_state=="running" else
                   "Offline incident detection is enabled but its required jobs are not running." if offline_state=="enabled" else
                   "Automatic offline incidents are turned off."),
        "last_attempt":None,
        "last_success":None,
        "last_error":None,
        "delivery_status":"not_applicable",
    }
    scan_query=db.query(NetworkScan).join(Device,NetworkScan.device_id==Device.id).join(Property,Device.property_id==Property.id)
    if organization_id:
        scan_query=scan_query.filter(Property.organization_id==organization_id)
    latest_scan=scan_query.order_by(NetworkScan.scanned_at.desc()).first()
    if latest_scan:
        offline_status["last_attempt"]=latest_scan.scanned_at.isoformat() if latest_scan.scanned_at else None
        offline_status["last_success"]=latest_scan.scanned_at.isoformat() if latest_scan.scanned_at else None
    return {
        "email_notifications":email_status,
        "daily_audit_email":audit_status,
        "automatic_offline_incidents":offline_status,
    }


def _local_operations_payload(db: Session, user: User, organization_id):
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Local operations dashboard could not verify database access")
        return {
            "service":{"status":"running","details":"HIOP responded to this request."},
            "database":{"status":"unavailable","details":"HIOP could not verify its database connection."},
            "scheduler":{"status":"running" if scheduler.running else "stopped","enabled_jobs":len(scheduler.get_jobs()) if scheduler.running else 0},
            "network":{"ipv4_addresses":[],"details":"Network details are unavailable while the database is offline."},
            "discovery":{"last_run":None,"result":"unavailable"},
            "monitored_devices":{"total":None},
            "backup":{"status":"unavailable","last_backup":None,"next_backup":None,"details":"Backup status is unavailable."},
            "storage":{"available_bytes":None,"database_bytes":None,"details":"Storage status is unavailable."},
            "recent_errors":[],
        }

    device_query=db.query(Device).join(Property,Device.property_id==Property.id).filter(
        Property.organization_id==organization_id,
        Device.inventory_status!="Retired",
    )
    latest_scan_query=db.query(NetworkScan).join(Device,NetworkScan.device_id==Device.id).join(
        Property,Device.property_id==Property.id
    ).filter(Property.organization_id==organization_id)
    latest_scan=latest_scan_query.order_by(NetworkScan.scanned_at.desc()).first()
    discovery_query=db.query(DiscoveryJob).join(Property,DiscoveryJob.property_id==Property.id).filter(
        Property.organization_id==organization_id
    )
    latest_discovery=discovery_query.order_by(DiscoveryJob.created_at.desc()).first()
    recent_errors=db.query(JobExecution).filter(
        JobExecution.organization_id==organization_id,
        JobExecution.status.in_(("FAILED","failed")),
    ).order_by(JobExecution.started_at.desc()).limit(5).all()

    try:
        local_ipv4=sorted({
            address[4][0]
            for address in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)
            if address[4][0]!="127.0.0.1"
        })
        network_details="Detected local IPv4 addresses for this HIOP server."
    except OSError:
        local_ipv4=[]
        network_details="HIOP could not determine this server's local IPv4 address."

    database_url=make_url(app_settings.database_url)
    is_local_sqlite=database_url.get_backend_name()=="sqlite"
    database_details=(
        "HIOP connected to its local private SQLite database."
        if is_local_sqlite else
        "HIOP connected to its managed database service."
    )
    storage={"available_bytes":None,"database_bytes":None,"details":"Storage usage is available for local SQLite installations only."}
    if is_local_sqlite and database_url.database and database_url.database!=":memory:":
        database_path=Path(database_url.database)
        if not database_path.is_absolute():
            database_path=Path.cwd()/database_path
        try:
            usage=shutil.disk_usage(database_path.resolve().parent)
            storage={
                "available_bytes":usage.free,
                "database_bytes":database_path.stat().st_size if database_path.exists() else None,
                "details":"Disk capacity and local database file size.",
            }
        except OSError:
            storage["details"]="HIOP could not read local storage usage."

    latest_backup=None
    latest_restore=None
    backup_details="Backup and restore history is managed by the platform administrator for hosted databases."
    backup_status="managed_by_platform"
    next_backup=None
    if is_local_sqlite:
        latest_backup=db.query(BackupRecord).order_by(BackupRecord.started_at.desc()).first()
        latest_restore=db.query(RestoreTest).order_by(RestoreTest.started_at.desc()).first()
        backup_status=latest_backup.status if latest_backup else "not_run"
        backup_details=(
            "No backup has been recorded yet."
            if not latest_backup else
            "The most recent backup is checksum-verified."
            if latest_backup.status=="success" and latest_backup.checksum_verified else
            "The most recent backup has not passed checksum verification."
            if latest_backup.status=="success" else
            "The most recent backup did not complete successfully."
        )
        if app_settings.scheduled_backup_enabled:
            now=datetime.now(timezone.utc)
            next_backup=now.replace(hour=app_settings.scheduled_backup_hour_utc,minute=0,second=0,microsecond=0)
            if next_backup<=now:
                next_backup+=timedelta(days=1)

    return {
        "service":{"status":"running","details":"HIOP responded to this request."},
        "database":{"status":"available","details":database_details},
        "scheduler":{"status":"running" if scheduler.running else "stopped","enabled_jobs":len(scheduler.get_jobs()) if scheduler.running else 0},
        "network":{"ipv4_addresses":local_ipv4,"details":network_details},
        "discovery":{
            "last_run":(latest_discovery.completed_at or latest_discovery.started_at or latest_discovery.created_at).isoformat() if latest_discovery else None,
            "result":latest_discovery.status if latest_discovery else "never_run",
            "hosts_completed":latest_discovery.hosts_completed if latest_discovery else 0,
            "hosts_total":latest_discovery.hosts_total if latest_discovery else 0,
        },
        "monitored_devices":{"total":device_query.count(),"last_scan":latest_scan.scanned_at.isoformat() if latest_scan and latest_scan.scanned_at else None,"last_result":latest_scan.status if latest_scan else None},
        "backup":{
            "status":backup_status,
            "last_backup":latest_backup.completed_at.isoformat() if latest_backup and latest_backup.completed_at else None,
            "last_backup_verified":bool(latest_backup and latest_backup.status=="success" and latest_backup.checksum_verified),
            "restore_status":latest_restore.status if latest_restore else "not_tested",
            "next_backup":next_backup.isoformat() if next_backup else None,
            "details":backup_details,
        },
        "storage":storage,
        "recent_errors":[
            {
                "job_type":error.job_type.replace("_"," ").capitalize(),
                "occurred_at":error.started_at.isoformat(),
                "message":f"A {error.job_type.replace('_',' ')} background task failed. Review service diagnostics before retrying.",
            }
            for error in recent_errors
        ],
    }


@router.get("/local-operations/status")
def local_operations_status(
    db: Session=Depends(get_db),
    user: User=Depends(require_roles(["admin"])),
    organization_id=Depends(organization_context),
):
    if user.organization_id and user.organization_id!=organization_id:
        raise HTTPException(403,"Organization is outside your permitted scope")
    return _local_operations_payload(db,user,organization_id)


@router.get("/local-operations/support-report")
def download_local_support_report(
    db: Session=Depends(get_db),
    user: User=Depends(require_roles(["admin"])),
    organization_id=Depends(organization_context),
):
    if user.organization_id and user.organization_id!=organization_id:
        raise HTTPException(403,"Organization is outside your permitted scope")
    payload=_local_operations_payload(db,user,organization_id)
    report={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "application":{"name":"HIOP","version":app_settings.app_version,"environment":app_settings.environment},
        "service":payload["service"],
        "database":payload["database"],
        "discovery":payload["discovery"],
        "monitored_devices":payload["monitored_devices"],
        "backup":payload["backup"],
        "storage":payload["storage"],
        "recent_errors":payload["recent_errors"],
        "privacy_notice":"This report excludes credentials, tokens, private keys, device addresses, MAC addresses, and backup file paths. Share it only with authorized HIOP support personnel.",
    }
    if payload["database"]["status"]=="available":
        create_audit_log(
            db,user.username,"LOCAL_SUPPORT_REPORT_DOWNLOADED","SupportReport","local",
            "Downloaded a redacted local operations support report",
            organization_id=organization_id,
        )
        db.commit()
    else:
        report["audit_logging"]="Unavailable because the database connection check failed."
    return Response(
        json.dumps(report,indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition":f'attachment; filename="hiop-support-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}.json"',
            "Cache-Control":"no-store",
        },
    )
