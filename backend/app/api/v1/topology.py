"""Secure manual-management APIs for the relational topology foundation."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.config import settings
from app.models.topology import (
    DeviceDependency, NetworkSegment, Topology, TopologyChange, TopologyGroup,
    TopologyLink, TopologyNode, TopologyNodePosition, TopologySnapshot,
    TopologySnapshotLink, TopologySnapshotNode,
)
from app.models.snmp import SNMPTarget
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.topology_neighbor import (
    TopologyNeighborCandidate, TopologyNeighborCollectionRun,
    TopologyNeighborObservation,
)
from app.models.topology_inference import (
    TopologyConflict, TopologyInferenceRun, TopologyReviewItem,
)
from app.schemas.topology import (
    BootstrapRequest, DependencyRead, DependencyWrite, LinkRead, LinkUpdate,
    LinkWrite, NodeRead, NodeUpdate, NodeWrite, PositionWrite, SegmentRead,
    SegmentWrite, SnapshotWrite, TopologyRead, TopologyUpdate, TopologyWrite,
)
from app.schemas.topology_neighbor import (
    CandidateMatchRequest, NeighborCandidateRead, NeighborCollectionRequest,
    NeighborObservationRead, NeighborRunRead, PerTargetCollectionRequest,
)
from app.schemas.topology_inference import (
    ConflictRead, InferenceRequest, InferenceRunRead, ReviewItemRead,
    ReviewResolution,
)
from app.services.audit_service import create_audit_log
from app.services.topology_service import TopologyService
from app.services.topology_neighbor_collection_service import TopologyNeighborCollectionService
from app.services.topology_inference_service import TopologyInferenceService
from app.websocket.connection_manager import manager

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


@router.post("/{topology_id}/collect-neighbors")
def collect_neighbors(topology_id: UUID, payload: NeighborCollectionRequest,
                      db: Session = Depends(get_db), actor=Depends(admin)):
    topology = _topology(db, topology_id)
    if len(payload.target_ids) > settings.topology_neighbor_maximum_targets:
        raise HTTPException(413, "Neighbor collection target limit was exceeded.")
    runs = []
    service = TopologyNeighborCollectionService(db)
    for target_id in payload.target_ids:
        target = db.get(SNMPTarget, target_id)
        if not target:
            raise HTTPException(404, f"SNMP target {target_id} was not found.")
        runs.append(service.collect(topology, target, payload.protocol_mode, payload.dry_run, actor))
    return {
        "accepted_target_count": len(runs),
        "collection_run_ids": [str(run.id) for run in runs],
        "protocol_selection": payload.protocol_mode,
        "dry_run": payload.dry_run,
        "warnings": [run.error_summary for run in runs if run.error_summary],
    }


@router.post("/{topology_id}/targets/{target_id}/collect-neighbors", response_model=NeighborRunRead)
def collect_target_neighbors(topology_id: UUID, target_id: UUID, payload: PerTargetCollectionRequest,
                             db: Session = Depends(get_db), actor=Depends(admin)):
    topology = _topology(db, topology_id)
    target = _get(db, SNMPTarget, target_id, "SNMP target")
    return TopologyNeighborCollectionService(db).collect(
        topology, target, payload.protocol_mode, payload.dry_run, actor
    )


@router.get("/{topology_id}/neighbor-runs")
def neighbor_runs(topology_id: UUID, page: int = Query(1, ge=1),
                  page_size: int = Query(50, ge=1, le=100),
                  target_id: UUID | None = None, status: str | None = None,
                  protocol: str | None = Query(None, pattern="^(lldp|cdp)$"),
                  db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologyNeighborCollectionRun).filter_by(topology_id=topology_id)
    if target_id:
        query = query.filter_by(target_id=target_id)
    if status:
        query = query.filter_by(status=status)
    if protocol:
        query = query.filter(TopologyNeighborCollectionRun.protocols_requested.contains([protocol]))
    return _page(query.order_by(TopologyNeighborCollectionRun.started_at.desc()), NeighborRunRead, page, page_size)


@router.get("/{topology_id}/neighbor-runs/{run_id}", response_model=NeighborRunRead)
def neighbor_run(topology_id: UUID, run_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    run = _get(db, TopologyNeighborCollectionRun, run_id, "Neighbor collection run")
    if run.topology_id != topology_id:
        raise HTTPException(404, "Neighbor collection run was not found in this topology.")
    return run


@router.post("/{topology_id}/neighbor-runs/{run_id}/cancel", response_model=NeighborRunRead)
def cancel_neighbor_run(topology_id: UUID, run_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    run = neighbor_run(topology_id, run_id, db)
    if run.status not in {"pending", "running"}:
        raise HTTPException(409, "Only an active neighbor collection can be cancelled.")
    run.cancellation_requested = True
    if run.status == "pending":
        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
    create_audit_log(db, actor.username, "TOPOLOGY_NEIGHBOR_COLLECTION_CANCEL_REQUESTED", "TopologyNeighborCollectionRun", str(run.id), "Requested neighbor collection cancellation.")
    db.commit()
    db.refresh(run)
    return run


@router.get("/{topology_id}/neighbor-runs/{run_id}/results")
def neighbor_run_results(topology_id: UUID, run_id: UUID, page: int = Query(1, ge=1),
                         page_size: int = Query(50, ge=1, le=100),
                         db: Session = Depends(get_db), _=Depends(reader)):
    neighbor_run(topology_id, run_id, db)
    query = db.query(TopologyNeighborObservation).filter_by(
        topology_id=topology_id, collection_run_id=run_id
    ).order_by(TopologyNeighborObservation.local_port_identifier)
    return _page(query, NeighborObservationRead, page, page_size)


@router.get("/{topology_id}/neighbor-observations")
def neighbor_observations(topology_id: UUID, page: int = Query(1, ge=1),
                          page_size: int = Query(50, ge=1, le=100),
                          source_target_id: UUID | None = None, protocol: str | None = None,
                          observation_status: str | None = None, conflict: bool | None = None,
                          search: str | None = Query(None, max_length=100),
                          db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologyNeighborObservation).filter_by(topology_id=topology_id)
    if source_target_id:
        query = query.filter_by(source_target_id=source_target_id)
    if protocol:
        query = query.filter_by(protocol=protocol)
    if observation_status:
        query = query.filter_by(observation_status=observation_status)
    if conflict is not None:
        query = query.filter(TopologyNeighborObservation.observation_status == "conflict" if conflict else TopologyNeighborObservation.observation_status != "conflict")
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            TopologyNeighborObservation.remote_system_name.ilike(term),
            TopologyNeighborObservation.remote_management_address.ilike(term),
            TopologyNeighborObservation.local_port_identifier.ilike(term),
        ))
    return _page(query.order_by(TopologyNeighborObservation.last_seen_at.desc()), NeighborObservationRead, page, page_size)


@router.get("/{topology_id}/neighbor-observations/{observation_id}", response_model=NeighborObservationRead)
def neighbor_observation(topology_id: UUID, observation_id: UUID,
                         db: Session = Depends(get_db), _=Depends(reader)):
    row = _get(db, TopologyNeighborObservation, observation_id, "Neighbor observation")
    if row.topology_id != topology_id:
        raise HTTPException(404, "Neighbor observation was not found in this topology.")
    return row


@router.get("/{topology_id}/neighbor-candidates")
def neighbor_candidates(topology_id: UUID, page: int = Query(1, ge=1),
                        page_size: int = Query(50, ge=1, le=100),
                        review_status: str | None = None,
                        db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologyNeighborCandidate).filter_by(topology_id=topology_id)
    if review_status:
        query = query.filter_by(review_status=review_status)
    return _page(query.order_by(TopologyNeighborCandidate.updated_at.desc()), NeighborCandidateRead, page, page_size)


@router.get("/{topology_id}/neighbor-candidates/{candidate_id}", response_model=NeighborCandidateRead)
def neighbor_candidate(topology_id: UUID, candidate_id: UUID,
                       db: Session = Depends(get_db), _=Depends(reader)):
    row = _get(db, TopologyNeighborCandidate, candidate_id, "Neighbor candidate")
    if row.topology_id != topology_id:
        raise HTTPException(404, "Neighbor candidate was not found in this topology.")
    return row


@router.post("/{topology_id}/neighbor-candidates/{candidate_id}/match", response_model=NeighborCandidateRead)
@router.post("/{topology_id}/neighbor-candidates/{candidate_id}/confirm-node-match", response_model=NeighborCandidateRead)
def match_neighbor_candidate(topology_id: UUID, candidate_id: UUID, payload: CandidateMatchRequest,
                             db: Session = Depends(get_db), actor=Depends(admin)):
    row = neighbor_candidate(topology_id, candidate_id, db)
    for key, value in payload.model_dump().items():
        setattr(row, f"matched_{key}", value)
    if payload.topology_node_id:
        node = _get(db, TopologyNode, payload.topology_node_id, "Topology node")
        if node.topology_id != topology_id:
            raise HTTPException(409, "Candidate match crosses topology boundaries.")
    if payload.device_id:
        _get(db, Device, payload.device_id, "Device")
    if payload.discovered_device_id:
        _get(db, DiscoveredDevice, payload.discovered_device_id, "Discovered device")
    if payload.snmp_target_id:
        _get(db, SNMPTarget, payload.snmp_target_id, "SNMP target")
    row.review_status = "matched"
    row.confidence_score = max(row.confidence_score, 85)
    create_audit_log(db, actor.username, "TOPOLOGY_NEIGHBOR_CANDIDATE_MATCHED", "TopologyNeighborCandidate", str(row.id), "Confirmed a reviewed neighbor candidate match.")
    db.commit()
    db.refresh(row)
    return row


@router.post("/{topology_id}/neighbor-candidates/{candidate_id}/ignore", response_model=NeighborCandidateRead)
def ignore_neighbor_candidate(topology_id: UUID, candidate_id: UUID,
                              db: Session = Depends(get_db), actor=Depends(admin)):
    row = neighbor_candidate(topology_id, candidate_id, db)
    row.review_status = "ignored"
    create_audit_log(db, actor.username, "TOPOLOGY_NEIGHBOR_CANDIDATE_IGNORED", "TopologyNeighborCandidate", str(row.id), "Ignored a neighbor candidate after review.")
    db.commit()
    db.refresh(row)
    return row


@router.post("/{topology_id}/neighbor-candidates/{candidate_id}/restore", response_model=NeighborCandidateRead)
def restore_neighbor_candidate(topology_id: UUID, candidate_id: UUID,
                               db: Session = Depends(get_db), actor=Depends(admin)):
    row = neighbor_candidate(topology_id, candidate_id, db)
    row.review_status = "pending"
    create_audit_log(db, actor.username, "TOPOLOGY_NEIGHBOR_CANDIDATE_RESTORED", "TopologyNeighborCandidate", str(row.id), "Restored a neighbor candidate for review.")
    db.commit()
    db.refresh(row)
    return row


@router.get("/{topology_id}/candidate-links")
def candidate_links(topology_id: UUID, page: int = Query(1, ge=1),
                    page_size: int = Query(50, ge=1, le=100),
                    db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologyLink).filter(
        TopologyLink.topology_id == topology_id,
        TopologyLink.discovery_method.in_(("LLDP", "CDP")),
        TopologyLink.is_manual.is_(False),
    ).order_by(TopologyLink.last_seen_at.desc())
    return _page(query, LinkRead, page, page_size)


@router.get("/{topology_id}/candidate-links/{link_id}", response_model=LinkRead)
def candidate_link(topology_id: UUID, link_id: UUID,
                   db: Session = Depends(get_db), _=Depends(reader)):
    row = get_link(topology_id, link_id, db)
    if row.is_manual or row.discovery_method not in {"LLDP", "CDP"}:
        raise HTTPException(404, "Candidate link was not found.")
    return row


@router.post("/{topology_id}/candidate-links/{link_id}/confirm", response_model=LinkRead)
def confirm_candidate_link(topology_id: UUID, link_id: UUID,
                           db: Session = Depends(get_db), actor=Depends(admin)):
    row = candidate_link(topology_id, link_id, db)
    _get(db, TopologyNode, row.source_node_id, "Source node")
    _get(db, TopologyNode, row.target_node_id, "Target node")
    conflicting = db.scalar(select(TopologyLink.id).where(
        TopologyLink.topology_id == topology_id,
        TopologyLink.id != row.id,
        TopologyLink.is_manual.is_(True), TopologyLink.is_confirmed.is_(True),
        or_(
            TopologyLink.source_interface_id == row.source_interface_id,
            TopologyLink.target_interface_id == row.source_interface_id,
        ) if row.source_interface_id else False,
    ))
    if conflicting:
        raise HTTPException(409, "A confirmed manual link has precedence on this interface.")
    row.is_confirmed = True
    row.status = "active"
    create_audit_log(db, actor.username, "TOPOLOGY_CANDIDATE_LINK_CONFIRMED", "TopologyLink", str(row.id), "Confirmed a reviewed protocol-discovered link.")
    db.commit()
    db.refresh(row)
    return row


@router.post("/{topology_id}/candidate-links/{link_id}/reject", response_model=LinkRead)
def reject_candidate_link(topology_id: UUID, link_id: UUID,
                          db: Session = Depends(get_db), actor=Depends(admin)):
    row = candidate_link(topology_id, link_id, db)
    row.status = "inactive"
    row.is_suppressed = True
    create_audit_log(db, actor.username, "TOPOLOGY_CANDIDATE_LINK_REJECTED", "TopologyLink", str(row.id), "Rejected a protocol-discovered candidate link.")
    db.commit()
    db.refresh(row)
    return row


@router.post("/{topology_id}/candidate-links/{link_id}/suppress", response_model=LinkRead)
def suppress_candidate_link(topology_id: UUID, link_id: UUID,
                            db: Session = Depends(get_db), actor=Depends(admin)):
    row = candidate_link(topology_id, link_id, db)
    row.is_suppressed = True
    create_audit_log(db, actor.username, "TOPOLOGY_CANDIDATE_LINK_SUPPRESSED", "TopologyLink", str(row.id), "Suppressed a protocol-discovered candidate link.")
    db.commit()
    db.refresh(row)
    return row


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


@router.get("/{topology_id}/inference")
def inference_state(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    topology = _topology(db, topology_id)
    latest = db.scalar(select(TopologyInferenceRun).where(
        TopologyInferenceRun.topology_id == topology_id
    ).order_by(TopologyInferenceRun.started_at.desc()))
    nodes = db.scalars(select(TopologyNode).where(TopologyNode.topology_id == topology_id)).all()
    links = db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology_id)).all()
    return {
        "topology_id": str(topology.id),
        "latest_run": InferenceRunRead.model_validate(latest) if latest else None,
        "open_conflicts": db.query(TopologyConflict).filter_by(topology_id=topology_id, status="open").count(),
        "pending_review_items": db.query(TopologyReviewItem).filter_by(topology_id=topology_id, status="pending").count(),
        "orphans": TopologyInferenceService.orphan_analysis(nodes, links),
    }


@router.post("/{topology_id}/run-inference", response_model=InferenceRunRead)
def run_inference(topology_id: UUID, payload: InferenceRequest,
                  db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyInferenceService(db).run(_topology(db, topology_id), payload, actor)


@router.get("/{topology_id}/conflicts")
def inference_conflicts(topology_id: UUID, page: int = Query(1, ge=1),
                        page_size: int = Query(50, ge=1, le=100),
                        status: str | None = None, severity: str | None = None,
                        db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologyConflict).filter_by(topology_id=topology_id)
    if status:
        query = query.filter_by(status=status)
    if severity:
        query = query.filter_by(severity=severity)
    return _page(query.order_by(TopologyConflict.detected_at.desc()), ConflictRead, page, page_size)


@router.get("/{topology_id}/review-items")
def review_items(topology_id: UUID, page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=100),
                 status: str | None = None, review_type: str | None = None,
                 db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    query = db.query(TopologyReviewItem).filter_by(topology_id=topology_id)
    if status:
        query = query.filter_by(status=status)
    if review_type:
        query = query.filter_by(review_type=review_type)
    return _page(query.order_by(TopologyReviewItem.created_at.desc()), ReviewItemRead, page, page_size)


def _review_item(db, topology_id, item_id):
    row = _get(db, TopologyReviewItem, item_id, "Topology review item")
    if row.topology_id != topology_id:
        raise HTTPException(404, "Topology review item was not found in this topology.")
    return row


def _apply_review(db, topology_id, row, actor):
    change = row.proposed_change or {}
    if row.review_type == "assign_layer":
        node = _get(db, TopologyNode, UUID(change["node_id"]), "Topology node")
        if node.topology_id != topology_id:
            raise HTTPException(409, "Review item references another topology.")
        before = node.layer
        node.layer = change["layer"]
        node.updated_by = actor.id
        db.add(TopologyChange(
            topology_id=topology_id, change_type="layer_changed",
            entity_type="node", node_id=node.id, source_type="reviewed_inference",
            confidence_score=row.confidence_score,
            previous_values={"layer": before}, current_values={"layer": node.layer},
        ))
    elif row.review_type == "create_dependency":
        upstream, downstream = UUID(change["upstream_node_id"]), UUID(change["downstream_node_id"])
        service = TopologyService(db)
        service._node(topology_id, upstream)
        service._node(topology_id, downstream)
        if service._dependency_reachable(topology_id, downstream, upstream):
            raise HTTPException(409, "Dependency would create a cycle.")
        exists = db.scalar(select(DeviceDependency).where(
            DeviceDependency.topology_id == topology_id,
            DeviceDependency.upstream_node_id == upstream,
            DeviceDependency.downstream_node_id == downstream,
            DeviceDependency.dependency_type == change.get("dependency_type", "network"),
        ))
        if not exists:
            db.add(DeviceDependency(
                topology_id=topology_id, upstream_node_id=upstream,
                downstream_node_id=downstream,
                dependency_type=change.get("dependency_type", "network"),
                source_type="reviewed_inference", confidence_score=row.confidence_score,
                is_manual=False, created_by=actor.id, updated_by=actor.id,
            ))
    elif row.review_type == "merge_nodes":
        canonical = _get(db, TopologyNode, UUID(change["canonical_node_id"]), "Canonical topology node")
        if canonical.topology_id != topology_id:
            raise HTTPException(409, "Canonical node belongs to another topology.")
        for duplicate_id in change.get("duplicate_node_ids", []):
            duplicate = _get(db, TopologyNode, UUID(duplicate_id), "Duplicate topology node")
            if duplicate.topology_id != topology_id:
                raise HTTPException(409, "Duplicate node belongs to another topology.")
            if canonical.device_id and duplicate.device_id and canonical.device_id != duplicate.device_id:
                raise HTTPException(409, "Official inventory nodes cannot be merged automatically.")
            links = db.scalars(select(TopologyLink).where(
                TopologyLink.topology_id == topology_id,
                or_(TopologyLink.source_node_id == duplicate.id, TopologyLink.target_node_id == duplicate.id),
            )).all()
            for link in links:
                other = link.target_node_id if link.source_node_id == duplicate.id else link.source_node_id
                if other == canonical.id:
                    link.status, link.is_suppressed = "inactive", True
                    link.metadata_json = {**(link.metadata_json or {}), "suppressed_during_node_merge": True}
                elif link.source_node_id == duplicate.id:
                    link.source_node_id = canonical.id
                else:
                    link.target_node_id = canonical.id
            duplicate.status = "merged"
            duplicate.is_hidden = True
            duplicate.metadata_json = {**(duplicate.metadata_json or {}), "merged_into": str(canonical.id)}
            db.add(TopologyChange(
                topology_id=topology_id, change_type="provisional_node_merged",
                entity_type="node", node_id=canonical.id, source_type="reviewed_inference",
                confidence_score=row.confidence_score,
                previous_values={"duplicate_node_id": str(duplicate.id)},
                current_values={"canonical_node_id": str(canonical.id)},
            ))
        create_audit_log(db, actor.username, "TOPOLOGY_NODE_MERGED", "TopologyNode", str(canonical.id), "Applied a reviewed provisional-node merge without modifying inventory.")


@router.post("/{topology_id}/review-items/{item_id}/approve", response_model=ReviewItemRead)
def approve_review_item(topology_id: UUID, item_id: UUID, payload: ReviewResolution,
                        db: Session = Depends(get_db), actor=Depends(admin)):
    row = _review_item(db, topology_id, item_id)
    if row.status != "pending":
        raise HTTPException(409, "Only a pending review item can be approved.")
    _apply_review(db, topology_id, row, actor)
    row.status, row.reviewed_by, row.reviewed_at = "approved", actor.id, datetime.now(timezone.utc)
    row.resolution_note = payload.note
    create_audit_log(db, actor.username, "TOPOLOGY_REVIEW_APPROVED", "TopologyReviewItem", str(row.id), "Approved and applied a topology inference review item.")
    db.commit()
    db.refresh(row)
    manager.broadcast_from_thread({"type": "topology_review_resolved", "topology_id": str(topology_id), "review_item_id": str(row.id), "status": row.status})
    manager.broadcast_from_thread({"type": "topology_graph_updated", "topology_id": str(topology_id), "review_item_id": str(row.id)})
    return row


def _resolve_review(topology_id, item_id, status, payload, db, actor):
    row = _review_item(db, topology_id, item_id)
    if row.status != "pending":
        raise HTTPException(409, "Only a pending review item can be resolved.")
    row.status, row.reviewed_by, row.reviewed_at = status, actor.id, datetime.now(timezone.utc)
    row.resolution_note = payload.note
    create_audit_log(db, actor.username, f"TOPOLOGY_REVIEW_{status.upper()}", "TopologyReviewItem", str(row.id), f"Marked topology review item {status}.")
    db.commit()
    db.refresh(row)
    manager.broadcast_from_thread({"type": "topology_review_resolved", "topology_id": str(topology_id), "review_item_id": str(row.id), "status": status})
    return row


@router.post("/{topology_id}/review-items/{item_id}/reject", response_model=ReviewItemRead)
def reject_review_item(topology_id: UUID, item_id: UUID, payload: ReviewResolution,
                       db: Session = Depends(get_db), actor=Depends(admin)):
    return _resolve_review(topology_id, item_id, "rejected", payload, db, actor)


@router.post("/{topology_id}/review-items/{item_id}/ignore", response_model=ReviewItemRead)
def ignore_review_item(topology_id: UUID, item_id: UUID, payload: ReviewResolution,
                       db: Session = Depends(get_db), actor=Depends(admin)):
    return _resolve_review(topology_id, item_id, "ignored", payload, db, actor)


@router.get("/{topology_id}/path-analysis")
def path_analysis(topology_id: UUID, source_node_id: UUID, target_node_id: UUID,
                  path_type: str = Query("any", pattern="^(physical|dependency|layer_aware|any)$"),
                  max_depth: int = Query(20, ge=1, le=100),
                  max_paths: int = Query(5, ge=1, le=20),
                  db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    TopologyService(db)._node(topology_id, source_node_id)
    TopologyService(db)._node(topology_id, target_node_id)
    links = db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology_id)).all()
    dependencies = db.scalars(select(DeviceDependency).where(DeviceDependency.topology_id == topology_id)).all()
    paths = TopologyInferenceService.reconstruct_paths(
        source_node_id, target_node_id, links, dependencies, path_type, max_depth,
        min(max_paths, settings.topology_inference_maximum_paths),
    )
    return {"paths": paths, "count": len(paths), "path_type": path_type}


@router.get("/{topology_id}/impact-analysis")
def impact_analysis(topology_id: UUID, node_id: UUID,
                    max_depth: int = Query(20, ge=1, le=100),
                    db: Session = Depends(get_db), _=Depends(reader)):
    topology = _topology(db, topology_id)
    impact_result = TopologyService(db).impact(topology.id, node_id, max_depth)
    nodes = db.scalars(select(TopologyNode).where(TopologyNode.topology_id == topology_id)).all()
    links = db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology_id)).all()
    return {**impact_result, "orphan_analysis": TopologyInferenceService.orphan_analysis(nodes, links)}


@router.get("/{topology_id}/comparison")
def compare_topology(topology_id: UUID, snapshot_id: UUID,
                     db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    return TopologyInferenceService(db).compare_snapshot(topology_id, snapshot_id)
