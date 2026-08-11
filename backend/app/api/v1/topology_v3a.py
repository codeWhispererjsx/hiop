"""V3A read-only topology APIs."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.services.topology_v3a_service import V3ATopologyService


router = APIRouter(prefix="/topology", tags=["V3A Network Topology"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
admin = require_roles(["admin"])


@router.get("")
def topology_graph(
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),
):
    return V3ATopologyService(db,organization_id=organization_id).graph(search)


@router.post("/refresh")
def refresh_topology(db: Session = Depends(get_db), actor=Depends(admin)):
    return V3ATopologyService(db).refresh(actor)


@router.get("/relationships/{relationship_id}")
def relationship_details(relationship_id: UUID, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context)):
    return V3ATopologyService(db,organization_id=organization_id).relationship(relationship_id)


@router.get("/devices/{device_id}/neighbors")
def device_neighbors(device_id: UUID, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context)):
    return V3ATopologyService(db,organization_id=organization_id).device_neighbors(device_id)


@router.get("/stats")
def topology_stats(db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context)):
    return V3ATopologyService(db,organization_id=organization_id).stats()
