"""Manual topology management, bounded graph queries, snapshots, and bootstrap."""
import hashlib
import json
from collections import deque
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.config import settings
from app.models.device import Device
from app.models.snmp import SNMPInterface
from app.models.topology import (
    DeviceDependency, NetworkSegment, Topology, TopologyChange, TopologyLink,
    TopologyNode, TopologyNodePosition, TopologySnapshot, TopologySnapshotLink,
    TopologySnapshotNode,
)
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager


class TopologyService:
    def __init__(self, db):
        self.db = db

    def add_node(self, topology, payload, actor):
        if self.db.query(TopologyNode).filter_by(topology_id=topology.id).count() >= settings.topology_maximum_nodes:
            raise HTTPException(413, "Topology node limit reached.")
        if payload.device_id:
            device = self.db.get(Device, payload.device_id)
            if not device:
                raise HTTPException(404, "Device was not found.")
            if self.db.scalar(select(TopologyNode).where(TopologyNode.topology_id == topology.id, TopologyNode.device_id == device.id)):
                raise HTTPException(409, "Device already has a node in this topology.")
        if payload.parent_node_id:
            self._node(topology.id, payload.parent_node_id)
        data = payload.model_dump()
        data["metadata_json"] = data.pop("metadata")
        node = TopologyNode(topology_id=topology.id, created_by=actor.id, updated_by=actor.id, **data)
        self.db.add(node); self.db.flush()
        self.db.add(TopologyChange(topology_id=topology.id, change_type="node_added", entity_type="node",
                                   node_id=node.id, current_values={"label": node.label}, source_type="manual"))
        create_audit_log(self.db, actor.username, "TOPOLOGY_NODE_ADDED", "TopologyNode", str(node.id), f"Added node '{node.label}'.")
        self.db.commit(); self.db.refresh(node)
        manager.broadcast_from_thread({"type": "topology_node_added", "topology_id": str(topology.id), "node_id": str(node.id)})
        return node

    def add_link(self, topology, payload, actor):
        if self.db.query(TopologyLink).filter_by(topology_id=topology.id).count() >= settings.topology_maximum_links:
            raise HTTPException(413, "Topology link limit reached.")
        source, target = self._node(topology.id, payload.source_node_id), self._node(topology.id, payload.target_node_id)
        for interface_id, node in ((payload.source_interface_id, source), (payload.target_interface_id, target)):
            if interface_id:
                interface = self.db.get(SNMPInterface, interface_id)
                if not interface:
                    raise HTTPException(404, "SNMP interface was not found.")
                if node.snmp_target_id and interface.target_id != node.snmp_target_id:
                    raise HTTPException(400, "Interface does not belong to the corresponding topology node target.")
        duplicate = self.db.scalar(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id, TopologyLink.status == "active",
            TopologyLink.source_interface_id == payload.source_interface_id,
            TopologyLink.target_interface_id == payload.target_interface_id,
            TopologyLink.source_node_id == source.id, TopologyLink.target_node_id == target.id,
        ))
        if duplicate:
            raise HTTPException(409, "An active link already exists for this endpoint/interface pair.")
        data = payload.model_dump(); data["metadata_json"] = data.pop("metadata")
        link = TopologyLink(topology_id=topology.id, created_by=actor.id, updated_by=actor.id, **data)
        self.db.add(link); self.db.flush()
        self.db.add(TopologyChange(topology_id=topology.id, change_type="link_added", entity_type="link",
                                   link_id=link.id, current_values={"source": str(source.id), "target": str(target.id)}))
        create_audit_log(self.db, actor.username, "TOPOLOGY_LINK_CREATED", "TopologyLink", str(link.id), "Created reviewed manual topology link.")
        self.db.commit(); self.db.refresh(link)
        manager.broadcast_from_thread({"type": "topology_link_added", "topology_id": str(topology.id), "link_id": str(link.id)})
        return link

    def add_dependency(self, topology, payload, actor):
        self._node(topology.id, payload.upstream_node_id); self._node(topology.id, payload.downstream_node_id)
        if self._dependency_reachable(topology.id, payload.downstream_node_id, payload.upstream_node_id):
            raise HTTPException(409, "Dependency would create a directed cycle.")
        row = DeviceDependency(topology_id=topology.id, created_by=actor.id, updated_by=actor.id, **payload.model_dump())
        self.db.add(row)
        create_audit_log(self.db, actor.username, "TOPOLOGY_DEPENDENCY_CREATED", "DeviceDependency", str(row.id), "Created manual dependency.")
        self.db.commit(); self.db.refresh(row)
        return row

    def graph(self, topology, include_hidden=False, minimum_confidence=0, search=None):
        query = select(TopologyNode).where(TopologyNode.topology_id == topology.id, TopologyNode.confidence_score >= minimum_confidence)
        if not include_hidden: query = query.where(TopologyNode.is_hidden.is_(False))
        if search: query = query.where(TopologyNode.label.ilike(f"%{search[:100]}%"))
        nodes = list(self.db.scalars(query.limit(settings.topology_maximum_graph_nodes)).all())
        ids = {row.id for row in nodes}
        links = list(self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id, TopologyLink.is_suppressed.is_(False),
            TopologyLink.source_node_id.in_(ids), TopologyLink.target_node_id.in_(ids),
        ).limit(settings.topology_maximum_graph_links)).all()) if ids else []
        return {"topology": topology, "nodes": nodes, "links": links, "groups": [], "segments": [],
                "metadata": {"node_count": len(nodes), "link_count": len(links), "generated_at": datetime.now(timezone.utc),
                             "bounded": len(nodes) >= settings.topology_maximum_graph_nodes}}

    def neighbors(self, topology_id, node_id):
        self._node(topology_id, node_id)
        links = self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology_id, TopologyLink.status == "active",
            TopologyLink.is_suppressed.is_(False),
            or_(TopologyLink.source_node_id == node_id, TopologyLink.target_node_id == node_id),
        )).all()
        ids = {link.target_node_id if link.source_node_id == node_id else link.source_node_id for link in links}
        return {"node_id": node_id, "nodes": list(self.db.scalars(select(TopologyNode).where(TopologyNode.id.in_(ids))).all()), "links": links}

    def shortest_path(self, topology_id, source, target, path_type="any", max_depth=None):
        self._node(topology_id, source); self._node(topology_id, target)
        depth_limit = min(max_depth or settings.topology_maximum_traversal_depth, settings.topology_maximum_traversal_depth)
        links = self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology_id, TopologyLink.status == "active", TopologyLink.is_suppressed.is_(False)
        ).limit(settings.topology_maximum_graph_links)).all()
        adjacency = {}
        for link in links:
            if path_type != "any" and link.link_type != path_type: continue
            adjacency.setdefault(link.source_node_id, []).append((link.target_node_id, link))
            if link.direction in {"bidirectional", "unknown"}:
                adjacency.setdefault(link.target_node_id, []).append((link.source_node_id, link))
        queue, seen = deque([(source, [source], [])]), {source}
        while queue:
            current, nodes, used = queue.popleft()
            if current == target:
                return {"found": True, "nodes": nodes, "links": [x.id for x in used], "depth": len(used), "accuracy": "structural_only"}
            if len(used) >= depth_limit: continue
            for neighbor, link in adjacency.get(current, []):
                if neighbor not in seen:
                    seen.add(neighbor); queue.append((neighbor, nodes + [neighbor], used + [link]))
        return {"found": False, "nodes": [], "links": [], "depth": 0, "accuracy": "structural_only"}

    def connected_components(self, topology_id):
        nodes = self.db.scalars(select(TopologyNode.id).where(TopologyNode.topology_id == topology_id).limit(settings.topology_maximum_graph_nodes)).all()
        remaining, components = set(nodes), []
        while remaining:
            root = next(iter(remaining)); component, queue = set(), [root]
            while queue:
                node = queue.pop()
                if node in component: continue
                component.add(node); remaining.discard(node)
                queue.extend(item.id for item in self.neighbors(topology_id, node)["nodes"] if item.id not in component)
            components.append(list(component))
        return {"components": components, "count": len(components), "bounded": len(nodes) >= settings.topology_maximum_graph_nodes}

    def impact(self, topology_id, node_id, max_depth=None):
        self._node(topology_id, node_id)
        limit = min(max_depth or settings.topology_maximum_traversal_depth, settings.topology_maximum_traversal_depth)
        dependencies = self.db.scalars(select(DeviceDependency).where(DeviceDependency.topology_id == topology_id, DeviceDependency.enabled.is_(True))).all()
        by_upstream = {}
        for row in dependencies: by_upstream.setdefault(row.upstream_node_id, []).append(row.downstream_node_id)
        queue, seen = deque([(node_id, 0)]), {node_id}
        while queue:
            current, depth = queue.popleft()
            if depth >= limit: continue
            for child in by_upstream.get(current, []):
                if child not in seen: seen.add(child); queue.append((child, depth + 1))
        affected = list(self.db.scalars(select(TopologyNode).where(TopologyNode.id.in_(seen - {node_id}))).all())
        return {"source_node_id": node_id, "potentially_affected_nodes": affected, "count": len(affected),
                "traversal_depth": limit, "confidence_note": "Structural potential impact only; this is not a routing or outage guarantee."}

    def snapshot(self, topology, payload, actor):
        nodes = self.db.scalars(select(TopologyNode).where(TopologyNode.topology_id == topology.id)).all()
        links = self.db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology.id)).all()
        if self.db.query(TopologySnapshot).filter_by(topology_id=topology.id).count() >= settings.topology_maximum_snapshots:
            raise HTTPException(413, "Topology snapshot limit reached.")
        snapshot = TopologySnapshot(topology_id=topology.id, created_by=actor.id, status="pending", **payload.model_dump())
        self.db.add(snapshot); self.db.flush()
        for node in nodes:
            self.db.add(TopologySnapshotNode(snapshot_id=snapshot.id, source_topology_node_id=node.id, device_id=node.device_id,
                label=node.label, node_type=node.node_type, status=node.status, role=node.role, layer=node.layer,
                management_ip=node.management_ip, metadata_json=node.metadata_json))
        for link in links:
            self.db.add(TopologySnapshotLink(snapshot_id=snapshot.id, source_topology_link_id=link.id,
                source_node_reference=link.source_node_id, target_node_reference=link.target_node_id,
                link_type=link.link_type, status=link.status, speed_bps=link.speed_bps, vlan_id=link.vlan_id,
                confidence_score=link.confidence_score, metadata_json=link.metadata_json))
        checksum = hashlib.sha256(json.dumps({"nodes": sorted(str(n.id) for n in nodes), "links": sorted(str(l.id) for l in links)}).encode()).hexdigest()
        snapshot.node_count, snapshot.link_count, snapshot.status = len(nodes), len(links), "completed"
        snapshot.completed_at, snapshot.checksum = datetime.now(timezone.utc), checksum
        create_audit_log(self.db, actor.username, "TOPOLOGY_SNAPSHOT_CREATED", "TopologySnapshot", str(snapshot.id), f"Captured {len(nodes)} nodes and {len(links)} links.")
        self.db.commit(); self.db.refresh(snapshot)
        return snapshot

    def bootstrap(self, topology, payload, actor):
        query = select(Device)
        if payload.include_only_active_inventory: query = query.where(Device.inventory_status == "Active")
        devices = self.db.scalars(query.limit(settings.topology_maximum_nodes)).all()
        existing = set(self.db.scalars(select(TopologyNode.device_id).where(TopologyNode.topology_id == topology.id, TopologyNode.device_id.isnot(None))).all())
        candidates = [d for d in devices if d.id not in existing]
        if payload.dry_run:
            return {"dry_run": True, "eligible": len(candidates), "created": 0, "links_created": 0}
        for device in candidates:
            self.db.add(TopologyNode(topology_id=topology.id, device_id=device.id, label=device.hostname,
                node_type=device.device_type.lower().replace(" ", "_"), status=device.network_status.lower(),
                management_ip=device.ip_address, vendor=device.brand, model=device.model, network_zone_id=device.network_zone_id,
                department_id=device.department_id, source_type="inventory", confidence_score=100, is_manual=False,
                created_by=actor.id, updated_by=actor.id))
        create_audit_log(self.db, actor.username, "TOPOLOGY_BOOTSTRAP_COMPLETED", "Topology", str(topology.id), f"Created {len(candidates)} inventory nodes and no links.")
        self.db.commit()
        manager.broadcast_from_thread({"type": "topology_bootstrap_completed", "topology_id": str(topology.id), "created": len(candidates)})
        return {"dry_run": False, "eligible": len(candidates), "created": len(candidates), "links_created": 0}

    def _node(self, topology_id, node_id):
        row = self.db.scalar(select(TopologyNode).where(TopologyNode.id == node_id, TopologyNode.topology_id == topology_id))
        if not row: raise HTTPException(404, "Topology node was not found in this topology.")
        return row

    def _dependency_reachable(self, topology_id, source, target):
        rows = self.db.scalars(select(DeviceDependency).where(DeviceDependency.topology_id == topology_id, DeviceDependency.enabled.is_(True))).all()
        graph = {}
        for row in rows: graph.setdefault(row.upstream_node_id, []).append(row.downstream_node_id)
        stack, seen = [source], set()
        while stack:
            node = stack.pop()
            if node == target: return True
            if node not in seen: seen.add(node); stack.extend(graph.get(node, []))
        return False
