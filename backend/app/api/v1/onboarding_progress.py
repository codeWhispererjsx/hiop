from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_db
from app.models.user import User
from app.models.hierarchy import Property
from app.models.local_agent import LocalAgentRegistration
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.discovered_device import DiscoveryRun
from app.models.alert import Alert

router = APIRouter(prefix="/onboarding", tags=["Onboarding Progress"])


@router.get("/progress")
def get_onboarding_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id

    # 1. Organization created – always true if the user has an org context
    org_created = org_id is not None

    # 2. Property created
    property_ids = [
        row[0]
        for row in db.query(Property.id)
        .filter(Property.organization_id == org_id)
        .all()
    ]
    prop_created = len(property_ids) > 0

    # 3. Discovery configured – at least one DiscoveryRun triggered by a user in this org
    user_ids = [
        row[0]
        for row in db.query(User.id)
        .filter(User.organization_id == org_id)
        .all()
    ]
    discovery_configured = False
    if user_ids:
        discovery_configured = (
            db.query(DiscoveryRun.id)
            .filter(DiscoveryRun.triggered_by.in_(user_ids))
            .first()
            is not None
        )

    # 4. Local agent connected
    agent_connected = (
        db.query(LocalAgentRegistration.id)
        .filter(LocalAgentRegistration.organization_id == org_id)
        .first()
        is not None
    )

    # 5. First network scan completed
    scan_run = False
    device_ids_query = db.query(Device.id).filter(
        Device.property_id.in_(property_ids)
    )
    if property_ids:
        scan_run = (
            db.query(NetworkScan.id)
            .filter(NetworkScan.device_id.in_(device_ids_query))
            .first()
            is not None
        )

    # 6. First devices approved into inventory
    devices_approved = False
    if property_ids:
        devices_approved = (
            db.query(Device.id)
            .filter(Device.property_id.in_(property_ids))
            .first()
            is not None
        )

    # 7. Monitoring configured – at least one alert has fired for a device in this org
    monitoring_configured = False
    if property_ids:
        monitoring_configured = (
            db.query(Alert.id)
            .filter(Alert.device_id.in_(device_ids_query))
            .first()
            is not None
        )

    return {
        "organization_created": org_created,
        "property_created": prop_created,
        "discovery_configured": discovery_configured,
        "agent_connected": agent_connected,
        "scan_run": scan_run,
        "devices_approved": devices_approved,
        "monitoring_configured": monitoring_configured,
    }

