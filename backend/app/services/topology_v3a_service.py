"""V3A read-only topology orchestration over existing inventory and SNMP evidence."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.config import settings
from app.models.device import Device
from app.models.snmp import SNMPInterface, SNMPTarget
from app.models.topology import Topology, TopologyLink, TopologyLinkEvidence, TopologyNode
from app.models.topology_neighbor import TopologyNeighborCandidate
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery
from app.services.snmp_client_service import SecureSNMPClient
from app.services.topology_neighbor_collection_service import TopologyNeighborCollectionService


BRIDGE_FDB_ADDRESS_OID = "1.3.6.1.2.1.17.4.3.1.1"
STALE_AFTER = timedelta(hours=24)
MINIMUM_RELATIONSHIP_CONFIDENCE = 60


def normalize_mac(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    compact = re.sub(r"[^0-9a-f]", "", text)
    if len(compact) != 12:
        return None
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def confidence_level(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


class SNMPMACTableProvider:
    """Bounded BRIDGE-MIB reader; it never issues an SNMP write operation."""

    def __init__(self, db, client_factory=SecureSNMPClient):
        self.db = db
        self.client_factory = client_factory

    def collect(self, target: SNMPTarget) -> set[str]:
        discovery = read_discovery(self.db)
        networks = discovery.get("authorized_cidr_ranges", [])
        ignored = discovery.get("ignore_ranges", [])
        if isinstance(networks, str):
            networks = [item.strip() for item in networks.split(",") if item.strip()]
        if isinstance(ignored, str):
            ignored = [item.strip() for item in ignored.split(",") if item.strip()]
        client = self.client_factory(
            target, target.credential, authorized_networks=networks, ignored_networks=ignored,
        )
        try:
            result = client.bulk_walk(
                BRIDGE_FDB_ADDRESS_OID,
                max_rows=min(settings.topology_neighbor_maximum_per_target, settings.snmp_maximum_walk_rows),
                max_duration=settings.topology_neighbor_maximum_duration_seconds,
            )
            return {
                mac for item in result.items
                if (mac := normalize_mac(item.value_text if item.value_text is not None else item.value_numeric))
            }
        finally:
            client.close()


class V3ATopologyService:
    def __init__(self, db, neighbor_factory=TopologyNeighborCollectionService, mac_provider=None, organization_id=None, property_id=None):
        self.db = db; self.organization_id=organization_id; self.property_id=property_id
        self.neighbor_factory = neighbor_factory
        self.mac_provider = mac_provider or SNMPMACTableProvider(db)

    def default_topology(self) -> Topology | None:
        return self.db.scalar(select(Topology).where(Topology.enabled.is_(True)).order_by(Topology.is_default.desc(), Topology.created_at))

    def ensure_default_topology(self, actor) -> Topology:
        topology = self.default_topology()
        if topology:
            return topology
        topology = Topology(
            name="HIOP Network Topology",
            description="Read-only relationships discovered from SNMP, LLDP, CDP and MAC-table evidence.",
            topology_type="physical", scope_type="global", enabled=True, is_default=True,
            layout_mode="hierarchical", created_by=actor.id, updated_by=actor.id,
        )
        self.db.add(topology)
        self.db.flush()
        create_audit_log(self.db, actor.username, "V3A_TOPOLOGY_CREATED", "Topology", str(topology.id), "Created the default read-only V3A topology.")
        self.db.commit()
        self.db.refresh(topology)
        return topology

    def node_for_device(self, topology: Topology, device: Device, actor) -> TopologyNode:
        node = self.db.scalar(select(TopologyNode).where(
            TopologyNode.topology_id == topology.id, TopologyNode.device_id == device.id,
        ))
        if not node:
            node = TopologyNode(
                topology_id=topology.id, device_id=device.id, label=device.hostname,
                node_type=device.device_type or "unknown", role="unknown", layer="unknown",
                status=device.network_status or "Unknown", management_ip=device.ip_address,
                vendor=device.brand, model=device.model, source_type="inventory",
                confidence_score=100, is_manual=False, created_by=actor.id, updated_by=actor.id,
                metadata_json={"inventory_identity": True},
            )
            self.db.add(node)
            self.db.flush()
        else:
            node.label = device.hostname
            node.node_type = device.device_type or "unknown"
            node.status = device.network_status or "Unknown"
            node.management_ip = device.ip_address
            node.vendor = device.brand
            node.model = device.model
        return node

    def upsert_relationship(
        self, topology: Topology, source: Device, destination: Device, relationship_type: str,
        evidence_source: str, confidence: int, actor, evidence_value: str | None = None,
        observed_at: datetime | None = None,
    ) -> tuple[TopologyLink | None, bool]:
        if source.id == destination.id or confidence < MINIMUM_RELATIONSHIP_CONFIDENCE:
            return None, False
        source_node = self.node_for_device(topology, source, actor)
        destination_node = self.node_for_device(topology, destination, actor)
        now = observed_at or datetime.now(timezone.utc)
        link = self.db.scalar(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id,
            or_(
                (TopologyLink.source_node_id == source_node.id) & (TopologyLink.target_node_id == destination_node.id),
                (TopologyLink.source_node_id == destination_node.id) & (TopologyLink.target_node_id == source_node.id),
            ),
            TopologyLink.link_type == relationship_type.lower(),
        ))
        created = link is None
        if not link:
            link = TopologyLink(
                topology_id=topology.id, source_node_id=source_node.id, target_node_id=destination_node.id,
                link_type=relationship_type.lower(), direction="source_to_target" if relationship_type != "NEIGHBOR_OF" else "bidirectional",
                status="active", source_type=evidence_source, discovery_method=evidence_source,
                confidence_score=confidence, first_seen_at=now, last_seen_at=now,
                is_manual=False, is_confirmed=False, created_by=actor.id, updated_by=actor.id,
                metadata_json={"confidence_level": confidence_level(confidence)},
            )
            self.db.add(link)
            self.db.flush()
        else:
            link.last_seen_at = now
            link.status = "active"
            link.missing_since = None
            link.confidence_score = max(link.confidence_score, confidence)
        existing_evidence = self.db.scalar(select(TopologyLinkEvidence.id).where(
            TopologyLinkEvidence.topology_link_id == link.id,
            TopologyLinkEvidence.source_type == evidence_source,
            TopologyLinkEvidence.evidence_value == evidence_value,
        ))
        if not existing_evidence:
            self.db.add(TopologyLinkEvidence(
                topology_link_id=link.id, source_type=evidence_source,
                source_reference=str(source.id), evidence_type=relationship_type.lower(),
                evidence_value=evidence_value, confidence_score=confidence, observed_at=now,
            ))
        return link, created

    def _apply_mac_associations(self, topology: Topology, observations: dict[str, list[SNMPTarget]], actor) -> tuple[int, int]:
        device_query = select(Device).where(Device.mac_address.is_not(None))
        if self.property_id:
            device_query = device_query.where(Device.property_id == self.property_id)
        devices = self.db.scalars(device_query).all()
        by_mac = defaultdict(list)
        for device in devices:
            if mac := normalize_mac(device.mac_address):
                by_mac[mac].append(device)
        created = unresolved = 0
        for mac, targets in observations.items():
            unique_targets = {target.id: target for target in targets}
            matches = by_mac.get(mac, [])
            if len(matches) != 1 or len(unique_targets) != 1:
                unresolved += 1
                continue
            target = next(iter(unique_targets.values()))
            switch = self.db.get(Device, target.device_id) if target.device_id else None
            endpoint = matches[0]
            if not switch or switch.id == endpoint.id:
                continue
            _, was_created = self.upsert_relationship(
                topology, switch, endpoint, "CONNECTED_TO", "SNMP_MAC_TABLE", 70, actor,
                evidence_value=f"MAC {mac} observed in the read-only bridge forwarding table",
            )
            created += int(was_created)
        return created, unresolved

    def mark_stale(self, topology: Topology, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        stale = 0
        for link in self.db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology.id)).all():
            if link.last_seen_at and now - link.last_seen_at > STALE_AFTER:
                if link.status != "stale":
                    link.status = "stale"
                    link.missing_since = link.missing_since or link.last_seen_at
                stale += 1
        return stale

    def refresh(self, actor) -> dict:
        topology = self.ensure_default_topology(actor)
        targets = self.db.scalars(select(SNMPTarget).where(
            SNMPTarget.enabled.is_(True), SNMPTarget.device_id.is_not(None),
            *( [SNMPTarget.device_id.in_(select(Device.id).where(Device.property_id == self.property_id))] if self.property_id else [] ),
        ).limit(settings.topology_neighbor_maximum_targets)).all()
        warnings: list[str] = []
        mac_observations: dict[str, list[SNMPTarget]] = defaultdict(list)
        completed = failed = 0
        if settings.snmp_enabled:
            for target in targets:
                try:
                    run = self.neighbor_factory(self.db).collect(topology, target, "auto", False, actor)
                    completed += int(run.status in {"completed", "partial"})
                    failed += int(run.status == "failed")
                    if run.error_summary:
                        warnings.append(run.error_summary)
                except (HTTPException, RuntimeError) as error:
                    failed += 1
                    warnings.append(getattr(error, "detail", None) or str(error))
                try:
                    for mac in self.mac_provider.collect(target):
                        mac_observations[mac].append(target)
                except Exception as error:
                    failed += 1
                    warnings.append(getattr(error, "safe_message", None) or "MAC-table evidence was unavailable.")
        mac_created, unresolved_mac = self._apply_mac_associations(topology, mac_observations, actor)
        stale = self.mark_stale(topology)
        create_audit_log(
            self.db, actor.username, "V3A_TOPOLOGY_REFRESHED", "Topology", str(topology.id),
            f"Read-only refresh completed for {completed}/{len(targets)} configured targets; {failed} failures.",
        )
        self.db.commit()
        status = "unavailable" if not settings.snmp_enabled or not targets else "partial" if failed else "complete"
        return {
            "status": status, "topology_id": str(topology.id), "targets_attempted": len(targets),
            "targets_completed": completed, "targets_failed": failed, "mac_relationships_created": mac_created,
            "unresolved_relationships": unresolved_mac, "stale_relationships": stale,
            "warnings": list(dict.fromkeys(warnings))[:25],
            "message": "Topology data unavailable because SNMP is not enabled or no linked targets exist." if status == "unavailable" else "Topology refresh completed." if status == "complete" else "Topology refresh completed with incomplete evidence.",
        }

    def graph(self, search: str | None = None) -> dict:
        topology = self.default_topology()
        if not topology:
            return {"topology": None, "nodes": [], "relationships": [], "data_state": "unavailable", "message": "Topology data unavailable. Refresh topology after configuring linked SNMP targets."}
        query = select(TopologyNode).where(TopologyNode.topology_id == topology.id, TopologyNode.device_id.is_not(None), TopologyNode.is_hidden.is_(False))
        nodes = list(self.db.scalars(query).all())
        device_query=select(Device).where(Device.id.in_([node.device_id for node in nodes]))
        if self.organization_id:
            from app.models.hierarchy import Property
            device_query=device_query.join(Property,Device.property_id==Property.id).where(Property.organization_id==self.organization_id)
        if self.property_id:
            device_query=device_query.where(Device.property_id==self.property_id)
        devices = {row.id: row for row in self.db.scalars(device_query).all()} if nodes else {}
        nodes=[node for node in nodes if node.device_id in devices]
        if search:
            value = search.lower()
            nodes = [node for node in nodes if value in " ".join(filter(None, [node.label, node.management_ip, node.vendor, node.node_type])).lower()]
        node_ids = {node.id for node in nodes}
        links = list(self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id, TopologyLink.is_suppressed.is_(False),
            TopologyLink.source_node_id.in_(node_ids), TopologyLink.target_node_id.in_(node_ids),
        )).all()) if node_ids else []
        payload_nodes = [self._node_payload(node, devices.get(node.device_id)) for node in nodes]
        payload_links = [self._link_payload(link) for link in links]
        targets = self.db.scalar(select(SNMPTarget.id).where(SNMPTarget.enabled.is_(True), SNMPTarget.device_id.is_not(None)))
        state = "current" if payload_links else "no_connections" if targets else "unavailable"
        message = None
        if state == "unavailable":
            message = "Topology data unavailable. Configure SNMP and link targets to existing devices."
        elif state == "no_connections":
            message = "No connections found from the available topology evidence."
        return {
            "topology": {"id": str(topology.id), "name": topology.name, "updated_at": topology.updated_at},
            "nodes": payload_nodes, "relationships": payload_links, "data_state": state, "message": message,
        }

    def relationship(self, relationship_id) -> dict:
        link = self.db.get(TopologyLink, relationship_id)
        if not link:
            raise HTTPException(404, "Topology relationship was not found.")
        if self.organization_id and str(link.id) not in {x["id"] for x in self.graph()["relationships"]}: raise HTTPException(404,"Topology relationship was not found.")
        return self._link_payload(link, include_evidence=True)

    def device_neighbors(self, device_id) -> dict:
        topology = self.default_topology()
        device = self.db.get(Device, device_id)
        if device and self.organization_id:
            from app.models.hierarchy import Property
            if not self.db.scalar(select(Property.id).where(Property.id==device.property_id,Property.organization_id==self.organization_id)):device=None
        if device and self.property_id and device.property_id != self.property_id:device=None
        if not device:
            raise HTTPException(404, "Device was not found.")
        if not topology:
            return {"device_id": str(device.id), "connections": [], "data_state": "unavailable", "message": "Topology data unavailable."}
        node = self.db.scalar(select(TopologyNode).where(TopologyNode.topology_id == topology.id, TopologyNode.device_id == device.id))
        if not node:
            return {"device_id": str(device.id), "connections": [], "data_state": "no_connections", "message": "No connections found for this device."}
        links = self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id, TopologyLink.is_suppressed.is_(False),
            or_(TopologyLink.source_node_id == node.id, TopologyLink.target_node_id == node.id),
        )).all()
        connections = []
        for link in links:
            neighbor_node_id = link.target_node_id if link.source_node_id == node.id else link.source_node_id
            neighbor_node = self.db.get(TopologyNode, neighbor_node_id)
            neighbor = self.db.get(Device, neighbor_node.device_id) if neighbor_node and neighbor_node.device_id else None
            if neighbor:
                connections.append({**self._link_payload(link), "neighbor": self._node_payload(neighbor_node, neighbor)})
        return {"device_id": str(device.id), "connections": connections, "data_state": "current" if connections else "no_connections", "message": None if connections else "No connections found for this device."}

    def stats(self) -> dict:
        graph = self.graph()
        relationships = graph["relationships"]
        return {
            "topology_relationships": len(relationships), "devices_represented": len(graph["nodes"]),
            "relationships_verified": sum(item["state"] == "current" for item in relationships),
            "stale_relationships": sum(item["state"] == "stale" for item in relationships),
            "unresolved_relationships": self.db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.review_status.in_(("pending", "unresolved", "conflict"))).count(),
            "duplicate_relationships": 0,
        }

    @staticmethod
    def _node_payload(node: TopologyNode, device: Device | None) -> dict:
        return {
            "id": str(node.id), "device_id": str(node.device_id), "label": node.label,
            "hostname": device.hostname if device else node.label, "ip_address": device.ip_address if device else node.management_ip,
            "device_type": device.device_type if device else node.node_type, "role": node.role or "unknown",
            "status": device.network_status if device else node.status, "vendor": device.brand if device else node.vendor,
            "model": device.model if device else node.model, "confidence": node.confidence_score,
        }

    def _link_payload(self, link: TopologyLink, include_evidence: bool = False) -> dict:
        source = link.source_type.replace("_", " ")
        state = "stale" if link.status in {"stale", "missing"} else "inactive" if link.status == "inactive" else "current"
        payload = {
            "id": str(link.id), "source_node_id": str(link.source_node_id), "destination_node_id": str(link.target_node_id),
            "relationship_type": link.link_type.upper(), "direction": link.direction,
            "evidence_source": source, "confidence": link.confidence_score,
            "confidence_level": confidence_level(link.confidence_score),
            "confidence_explanation": f"{confidence_level(link.confidence_score).title()} confidence from {source} evidence matched to existing inventory identities.",
            "first_discovered_at": link.first_seen_at, "last_verified_at": link.last_seen_at,
            "state": state, "active": state == "current",
            "source_port": self._port_payload(link.source_interface_id),
            "destination_port": self._port_payload(link.target_interface_id),
            "vlan_id": link.vlan_id,
            "vlan_name": (link.metadata_json or {}).get("vlan_name"),
        }
        if include_evidence:
            payload["evidence"] = [
                {"source": row.source_type, "type": row.evidence_type, "value": row.evidence_value, "confidence": row.confidence_score, "observed_at": row.observed_at}
                for row in self.db.scalars(select(TopologyLinkEvidence).where(TopologyLinkEvidence.topology_link_id == link.id).order_by(TopologyLinkEvidence.observed_at.desc())).all()
            ]
        return payload

    def _port_payload(self, interface_id):
        interface = self.db.get(SNMPInterface, interface_id) if interface_id else None
        if not interface:
            return None
        status = {"1": "up", "2": "down", "3": "testing"}
        return {
            "id": str(interface.id), "name": interface.name,
            "description": interface.description,
            "admin_status": status.get(str(interface.admin_status), str(interface.admin_status or "unknown").lower()),
            "operational_status": status.get(str(interface.operational_status), str(interface.operational_status or "unknown").lower()),
            "speed_bps": interface.speed_bps, "duplex": interface.duplex,
            "last_observed_at": interface.last_seen_at,
        }
