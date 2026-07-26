"""Secure manual-management APIs for the relational topology foundation."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.topology import (
    DeviceDependency, NetworkSegment, Topology, TopologyChange, TopologyGroup,
    TopologyLink, TopologyNode, TopologyNodePosition, TopologySnapshot,
    TopologySnapshotLink, TopologySnapshotNode,
)
from app.schemas.topology import (
    BootstrapRequest, DependencyRead, DependencyWrite, LinkRead, LinkUpdate,
    LinkWrite, NodeRead, NodeUpdate, NodeWrite, PositionWrite, SegmentRead,
    SegmentWrite, SnapshotWrite, TopologyRead, TopologyUpdate, TopologyWrite,
)
from app.services.audit_service import create_audit_log
from app.services.topology_service import TopologyService

router = APIRouter(prefix="/topology", tags=["Topology"])
admin = require_roles(["admin"])
reader = require_roles(["admin", "technician"])


def _get(db, model, object_id, label):
    row = db.get(model, object_id)
    if not row: raise HTTPException(404, f"{label} was not found.")
    return row


def _topology(db, topology_id):
    return _get(db, Topology, topology_id, "Topology")


def _page(query, schema, page, page_size):
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [schema.model_validate(x) for x in rows], "total": total, "page": page, "page_size": page_size}


@router.get("")
def list_topologies(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                    enabled: bool | None = None, db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(Topology)
    if enabled is not None: query = query.filter_by(enabled=enabled)
    return _page(query.order_by(Topology.name), TopologyRead, page, page_size)


@router.post("", response_model=TopologyRead, status_code=201)
def create_topology(payload: TopologyWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    if payload.is_default: db.query(Topology).update({Topology.is_default: False})
    row = Topology(**payload.model_dump(), created_by=actor.id, updated_by=actor.id)
    db.add(row)
    create_audit_log(db, actor.username, "TOPOLOGY_CREATED", "Topology", str(row.id), f"Created topology '{row.name}'.")
    db.commit(); db.refresh(row)
    return row


@router.post("/bootstrap")
def bootstrap(topology_id: UUID, payload: BootstrapRequest, db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyService(db).bootstrap(_topology(db, topology_id), payload, actor)


@router.get("/{topology_id}", response_model=TopologyRead)
def get_topology(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return _topology(db, topology_id)


@router.patch("/{topology_id}", response_model=TopologyRead)
def update_topology(topology_id: UUID, payload: TopologyUpdate, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _topology(db, topology_id)
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_by = actor.id
    create_audit_log(db, actor.username, "TOPOLOGY_UPDATED", "Topology", str(row.id), f"Updated topology '{row.name}'.")
    db.commit(); db.refresh(row)
    return row


@router.post("/{topology_id}/enable", response_model=TopologyRead)
def enable(topology_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_topology(topology_id, TopologyUpdate(enabled=True), db, actor)


@router.post("/{topology_id}/disable", response_model=TopologyRead)
def disable(topology_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_topology(topology_id, TopologyUpdate(enabled=False), db, actor)


@router.post("/{topology_id}/set-default", response_model=TopologyRead)
def set_default(topology_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _topology(db, topology_id)
    db.query(Topology).filter(Topology.id != row.id).update({Topology.is_default: False})
    row.is_default = True
    create_audit_log(db, actor.username, "TOPOLOGY_DEFAULT_CHANGED", "Topology", str(row.id), "Changed the default topology.")
    db.commit(); db.refresh(row)
    return row


@router.get("/{topology_id}/nodes")
def nodes(topology_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
          search: str | None = Query(None, max_length=100), hidden: bool | None = None,
          db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id); query = db.query(TopologyNode).filter_by(topology_id=topology_id)
    if search: query = query.filter(TopologyNode.label.ilike(f"%{search}%"))
    if hidden is not None: query = query.filter_by(is_hidden=hidden)
    return _page(query.order_by(TopologyNode.label), NodeRead, page, page_size)


@router.post("/{topology_id}/nodes", response_model=NodeRead, status_code=201)
def add_node(topology_id: UUID, payload: NodeWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyService(db).add_node(_topology(db, topology_id), payload, actor)


@router.get("/{topology_id}/nodes/{node_id}", response_model=NodeRead)
def get_node(topology_id: UUID, node_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return TopologyService(db)._node(topology_id, node_id)


@router.patch("/{topology_id}/nodes/{node_id}", response_model=NodeRead)
def update_node(topology_id: UUID, node_id: UUID, payload: NodeUpdate, db: Session = Depends(get_db), actor=Depends(admin)):
    service = TopologyService(db); row = service._node(topology_id, node_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "parent_node_id" and value: service._node(topology_id, value)
        setattr(row, key, value)
    row.updated_by = actor.id
    create_audit_log(db, actor.username, "TOPOLOGY_NODE_UPDATED", "TopologyNode", str(row.id), "Updated topology node.")
    db.commit(); db.refresh(row)
    return row


@router.post("/{topology_id}/nodes/{node_id}/hide", response_model=NodeRead)
def hide_node(topology_id: UUID, node_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_node(topology_id, node_id, NodeUpdate(is_hidden=True), db, actor)


@router.post("/{topology_id}/nodes/{node_id}/restore", response_model=NodeRead)
def restore_node(topology_id: UUID, node_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_node(topology_id, node_id, NodeUpdate(is_hidden=False), db, actor)


@router.get("/{topology_id}/links")
def links(topology_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
          status: str | None = None, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id); query = db.query(TopologyLink).filter_by(topology_id=topology_id)
    if status: query = query.filter_by(status=status)
    return _page(query.order_by(TopologyLink.created_at.desc()), LinkRead, page, page_size)


@router.post("/{topology_id}/links", response_model=LinkRead, status_code=201)
def add_link(topology_id: UUID, payload: LinkWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyService(db).add_link(_topology(db, topology_id), payload, actor)


@router.get("/{topology_id}/links/{link_id}", response_model=LinkRead)
def get_link(topology_id: UUID, link_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    row = _get(db, TopologyLink, link_id, "Topology link")
    if row.topology_id != topology_id: raise HTTPException(404, "Topology link was not found in this topology.")
    return row


@router.patch("/{topology_id}/links/{link_id}", response_model=LinkRead)
def update_link(topology_id: UUID, link_id: UUID, payload: LinkUpdate, db: Session = Depends(get_db), actor=Depends(admin)):
    row = get_link(topology_id, link_id, db)
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_by = actor.id
    create_audit_log(db, actor.username, "TOPOLOGY_LINK_UPDATED", "TopologyLink", str(row.id), "Updated topology link.")
    db.commit(); db.refresh(row)
    return row


@router.post("/{topology_id}/links/{link_id}/confirm", response_model=LinkRead)
def confirm_link(topology_id: UUID, link_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_link(topology_id, link_id, LinkUpdate(is_confirmed=True), db, actor)


@router.post("/{topology_id}/links/{link_id}/suppress", response_model=LinkRead)
def suppress_link(topology_id: UUID, link_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_link(topology_id, link_id, LinkUpdate(is_suppressed=True), db, actor)


@router.post("/{topology_id}/links/{link_id}/restore", response_model=LinkRead)
def restore_link(topology_id: UUID, link_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_link(topology_id, link_id, LinkUpdate(is_suppressed=False, status="active"), db, actor)


@router.get("/{topology_id}/graph")
def graph(topology_id: UUID, include_hidden: bool = False, confidence_minimum: int = Query(0, ge=0, le=100),
          search: str | None = Query(None, max_length=100), db: Session = Depends(get_db), _=Depends(reader)):
    return TopologyService(db).graph(_topology(db, topology_id), include_hidden, confidence_minimum, search)


@router.get("/{topology_id}/neighbors/{node_id}")
def neighbors(topology_id: UUID, node_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return TopologyService(db).neighbors(topology_id, node_id)


@router.get("/{topology_id}/connected-components")
def components(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id); return TopologyService(db).connected_components(topology_id)


@router.get("/{topology_id}/path")
def path(topology_id: UUID, source_node_id: UUID, target_node_id: UUID,
         path_type: str = Query("any", pattern="^(physical|logical|dependency|any)$"),
         max_depth: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    return TopologyService(db).shortest_path(topology_id, source_node_id, target_node_id, path_type, max_depth)


@router.get("/{topology_id}/impact/{node_id}")
def impact(topology_id: UUID, node_id: UUID, max_depth: int = Query(20, ge=1, le=100),
           db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id); return TopologyService(db).impact(topology_id, node_id, max_depth)


@router.get("/{topology_id}/segments")
def segments(topology_id: UUID, page: int = 1, page_size: int = Query(50, ge=1, le=100),
             db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    return _page(db.query(NetworkSegment).filter_by(topology_id=topology_id), SegmentRead, page, page_size)


@router.post("/{topology_id}/segments", response_model=SegmentRead, status_code=201)
def add_segment(topology_id: UUID, payload: SegmentWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id); row = NetworkSegment(topology_id=topology_id, **payload.model_dump())
    db.add(row); create_audit_log(db, actor.username, "TOPOLOGY_SEGMENT_CREATED", "NetworkSegment", str(row.id), "Created network segment.")
    db.commit(); db.refresh(row); return row


@router.patch("/{topology_id}/segments/{segment_id}", response_model=SegmentRead)
def update_segment(topology_id: UUID, segment_id: UUID, payload: SegmentWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, NetworkSegment, segment_id, "Network segment")
    if row.topology_id != topology_id: raise HTTPException(404, "Network segment was not found in this topology.")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    create_audit_log(db, actor.username, "TOPOLOGY_SEGMENT_UPDATED", "NetworkSegment", str(row.id), "Updated network segment.")
    db.commit(); db.refresh(row); return row


@router.get("/{topology_id}/dependencies")
def dependencies(topology_id: UUID, page: int = 1, page_size: int = Query(50, ge=1, le=100),
                 db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    return _page(db.query(DeviceDependency).filter_by(topology_id=topology_id), DependencyRead, page, page_size)


@router.post("/{topology_id}/dependencies", response_model=DependencyRead, status_code=201)
def add_dependency(topology_id: UUID, payload: DependencyWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyService(db).add_dependency(_topology(db, topology_id), payload, actor)


@router.get("/{topology_id}/layout")
def layout(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id); rows = db.query(TopologyNodePosition).filter_by(topology_id=topology_id).all()
    return {"items": rows, "total": len(rows)}


@router.put("/{topology_id}/layout")
def put_layout(topology_id: UUID, payload: list[PositionWrite],
               db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id)
    if len(payload) > 2000: raise HTTPException(413, "Layout update exceeds the safe node limit.")
    for item in payload:
        TopologyService(db)._node(topology_id, item.node_id)
        row = db.scalar(select(TopologyNodePosition).where(TopologyNodePosition.topology_id == topology_id, TopologyNodePosition.node_id == item.node_id))
        if not row: row = TopologyNodePosition(topology_id=topology_id, node_id=item.node_id); db.add(row)
        for key, value in item.model_dump().items(): setattr(row, key, value)
        row.updated_by = actor.id
    create_audit_log(db, actor.username, "TOPOLOGY_LAYOUT_UPDATED", "Topology", str(topology_id), f"Updated {len(payload)} positions.")
    db.commit(); return {"updated": len(payload)}


@router.get("/{topology_id}/snapshots")
def snapshots(topology_id: UUID, page: int = 1, page_size: int = Query(50, ge=1, le=100),
              db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologySnapshot).filter_by(topology_id=topology_id).order_by(TopologySnapshot.created_at.desc())
    total = query.count(); rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.post("/{topology_id}/snapshots", status_code=201)
def create_snapshot(topology_id: UUID, payload: SnapshotWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyService(db).snapshot(_topology(db, topology_id), payload, actor)


@router.get("/{topology_id}/snapshots/{snapshot_id}/graph")
def snapshot_graph(topology_id: UUID, snapshot_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    snapshot = _get(db, TopologySnapshot, snapshot_id, "Topology snapshot")
    if snapshot.topology_id != topology_id: raise HTTPException(404, "Snapshot was not found in this topology.")
    return {"snapshot": snapshot, "nodes": db.query(TopologySnapshotNode).filter_by(snapshot_id=snapshot.id).all(),
            "links": db.query(TopologySnapshotLink).filter_by(snapshot_id=snapshot.id).all()}


@router.get("/{topology_id}/stats")
def stats(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    nodes = db.query(TopologyNode).filter_by(topology_id=topology_id).count()
    links = db.query(TopologyLink).filter_by(topology_id=topology_id).count()
    active = db.query(TopologyLink).filter_by(topology_id=topology_id, status="active", is_suppressed=False).count()
    components = TopologyService(db).connected_components(topology_id)
    return {"nodes": nodes, "links": links, "active_links": active,
            "confirmed_links": db.query(TopologyLink).filter_by(topology_id=topology_id, is_confirmed=True).count(),
            "segments": db.query(NetworkSegment).filter_by(topology_id=topology_id).count(),
            "snapshots": db.query(TopologySnapshot).filter_by(topology_id=topology_id).count(),
            "pending_changes": db.query(TopologyChange).filter_by(topology_id=topology_id, review_status="pending").count(),
            "connected_components": components["count"], "orphan_nodes": max(0, nodes - active * 2)}


@router.get("/{topology_id}/orphans")
def orphans(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    linked = select(TopologyLink.source_node_id).where(TopologyLink.topology_id == topology_id, TopologyLink.status == "active").union(
        select(TopologyLink.target_node_id).where(TopologyLink.topology_id == topology_id, TopologyLink.status == "active"))
    rows = db.scalars(select(TopologyNode).where(TopologyNode.topology_id == topology_id, TopologyNode.id.not_in(linked),
                                                TopologyNode.node_type.not_in(("external_network", "internet")))).all()
    return {"items": rows, "total": len(rows)}


@router.get("/{topology_id}/changes")
def changes(topology_id: UUID, page: int = 1, page_size: int = Query(50, ge=1, le=100),
            db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id); query = db.query(TopologyChange).filter_by(topology_id=topology_id).order_by(TopologyChange.detected_at.desc())
    total = query.count(); return {"items": query.offset((page-1)*page_size).limit(page_size).all(), "total": total, "page": page, "page_size": page_size}


@router.post("/{topology_id}/changes/{change_id}/confirm")
def confirm_change(topology_id: UUID, change_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, TopologyChange, change_id, "Topology change")
    if row.topology_id != topology_id: raise HTTPException(404, "Change was not found in this topology.")
    row.review_status, row.reviewed_by, row.reviewed_at = "confirmed", actor.id, datetime.now(timezone.utc)
    create_audit_log(db, actor.username, "TOPOLOGY_CHANGE_REVIEWED", "TopologyChange", str(row.id), "Confirmed topology change.")
    db.commit(); return row


@router.post("/{topology_id}/changes/{change_id}/ignore")
def ignore_change(topology_id: UUID, change_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    row = confirm_change(topology_id, change_id, db, actor); row.review_status = "ignored"; db.commit(); return row
