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
from app.models.onboarding_state import PropertyOnboardingState, OnboardingState

router = APIRouter(prefix="/onboarding", tags=["Onboarding Progress"])


@router.get("/progress")
def get_onboarding_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id
    property_id = current_user.primary_location_id if current_user.primary_location_type == "property" else None
    
    # Try to get existing onboarding state
    onboarding_state = None
    if property_id:
        onboarding_state = db.query(PropertyOnboardingState).filter(
            PropertyOnboardingState.property_id == property_id
        ).first()
    
    # If no state exists, create one
    if not onboarding_state and property_id:
        onboarding_state = PropertyOnboardingState(
            property_id=property_id,
            organization_id=org_id,
            state=OnboardingState.IN_PROGRESS.value,
            organization_configured=True,  # Assume org is configured if user exists
            current_step="organization_configured",
            started_at=None,
            steps_completed=1,
        )
        db.add(onboarding_state)
        db.commit()
    
    # If still no state (no property), return basic progress
    if not onboarding_state:
        # Basic progress tracking for organizations without onboarding state
        property_ids = [
            row[0]
            for row in db.query(Property.id)
            .filter(Property.organization_id == org_id)
            .all()
        ]
        return {
            "state": "in_progress",
            "checklist": {
                "organization_configured": True,
                "departments_configured": False,
                "locations_configured": False,
                "agent_connected": False,
                "network_configured": False,
                "discovery_run": False,
                "devices_reviewed": False,
                "devices_approved": False,
                "monitoring_configured": False,
            },
            "current_step": "organization_configured",
            "progress_percentage": 12.5,  # 1/8 steps
            "steps_completed": 1,
            "total_steps": 8,
        }
    
    # Update checklist dynamically based on actual system state
    if property_id:
        # Check agent connection
        onboarding_state.agent_connected = db.query(LocalAgentRegistration.id).filter(
            LocalAgentRegistration.property_id == property_id
        ).first() is not None
        
        # Check discovery runs
        onboarding_state.discovery_run = db.query(DiscoveryRun.id).filter(
            DiscoveryRun.property_id == property_id
        ).first() is not None
        
        # Check devices
        onboarding_state.devices_approved = db.query(Device.id).filter(
            Device.property_id == property_id
        ).first() is not None
        
        # Check monitoring (alerts)
        device_ids_query = db.query(Device.id).filter(Device.property_id == property_id)
        onboarding_state.monitoring_configured = db.query(Alert.id).filter(
            Alert.device_id.in_(device_ids_query)
        ).first() is not None
        
        # Update steps completed count
        checklist = onboarding_state.get_checklist()
        completed_count = sum(1 for v in checklist.values() if v)
        onboarding_state.steps_completed = completed_count
        
        # Update state if core complete
        if onboarding_state.is_core_complete() and onboarding_state.state != OnboardingState.COMPLETED.value:
            onboarding_state.state = OnboardingState.COMPLETED.value
            onboarding_state.completed_at = None  # Will be set when explicitly completed
            onboarding_state.current_step = "completed"
        
        db.commit()
    
    return {
        "state": onboarding_state.state,
        "checklist": onboarding_state.get_checklist(),
        "current_step": onboarding_state.current_step,
        "progress_percentage": onboarding_state.get_progress_percentage(),
        "steps_completed": onboarding_state.steps_completed,
        "total_steps": onboarding_state.total_steps,
        "started_at": onboarding_state.started_at.isoformat() if onboarding_state.started_at else None,
        "completed_at": onboarding_state.completed_at.isoformat() if onboarding_state.completed_at else None,
    }


@router.post("/complete")
def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark onboarding as complete"""
    property_id = current_user.primary_location_id if current_user.primary_location_type == "property" else None
    
    if not property_id:
        return {"error": "No property context"}
    
    onboarding_state = db.query(PropertyOnboardingState).filter(
        PropertyOnboardingState.property_id == property_id
    ).first()
    
    if not onboarding_state:
        return {"error": "No onboarding state found"}
    
    onboarding_state.state = OnboardingState.COMPLETED.value
    onboarding_state.completed_at = datetime.now(timezone.utc)
    onboarding_state.current_step = "completed"
    db.commit()
    
    return {"message": "Onboarding marked as complete"}


@router.post("/skip")
def skip_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Skip onboarding"""
    property_id = current_user.primary_location_id if current_user.primary_location_type == "property" else None
    
    if not property_id:
        return {"error": "No property context"}
    
    onboarding_state = db.query(PropertyOnboardingState).filter(
        PropertyOnboardingState.property_id == property_id
    ).first()
    
    if not onboarding_state:
        return {"error": "No onboarding state found"}
    
    onboarding_state.state = OnboardingState.SKIPPED.value
    onboarding_state.completed_at = datetime.now(timezone.utc)
    onboarding_state.current_step = "skipped"
    db.commit()
    
    return {"message": "Onboarding skipped"}

