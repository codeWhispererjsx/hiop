"""Collection, normalization and conservative staging of LLDP/CDP evidence."""
from datetime import datetime, timezone
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.snmp import SNMPDeviceProfile, SNMPInterface, SNMPTarget
from app.models.topology import (
    Topology, TopologyChange, TopologyLink, TopologyLinkEvidence, TopologyNode,
)
from app.models.topology_neighbor import (
    TopologyNeighborCandidate, TopologyNeighborCollectionRun,
    TopologyNeighborObservation,
)
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery
from app.services.snmp_client_service import SNMPClientError, SecureSNMPClient
from app.services.snmp_runtime import snmp_operation_lock
from app.services.snmp_notification_service import notify_snmp
from app.services.topology_neighbor_parser import (
    CDP_OIDS, LLDP_OIDS, NormalizedNeighbor, parse_cdp_rows, parse_lldp_rows,
    tabular_walks,
)
from app.websocket.connection_manager import manager


class TopologyNeighborCollectionService:
    def __init__(self, db, collector=None):
        self.db = db
        self.collector = collector

    def protocols(self, target, mode):
        profile = self.db.get(SNMPDeviceProfile, target.detected_profile_id) if target.detected_profile_id else None
        vendor = (getattr(profile, "vendor", "") or "").lower()
        profile_data = getattr(profile, "profile_data", {}) or {}
        cdp_supported = "cisco" in vendor or profile_data.get("supports_cdp") is True
        if mode == "lldp":
            return ["lldp"]
        if mode == "cdp":
            if not cdp_supported:
                raise HTTPException(409, "CDP collection requires a supported Cisco/device profile.")
            return ["cdp"]
        if mode == "both":
            if not cdp_supported:
                raise HTTPException(409, "CDP collection requires a supported Cisco/device profile.")
            return ["lldp", "cdp"]
        return ["lldp", "cdp"] if "cisco" in vendor else ["lldp"]

    def _live_rows(self, target, protocols, cancelled):
        discovery = read_discovery(self.db)
        networks = discovery.get("authorized_cidr_ranges", [])
        ignored = discovery.get("ignore_ranges", [])
        if isinstance(networks, str):
            networks = [value.strip() for value in networks.split(",") if value.strip()]
        if isinstance(ignored, str):
            ignored = [value.strip() for value in ignored.split(",") if value.strip()]
        client = SecureSNMPClient(
            target, target.credential, authorized_networks=networks,
            ignored_networks=ignored,
        )
        output = {}
        try:
            for protocol in protocols:
                oid_map = LLDP_OIDS if protocol == "lldp" else CDP_OIDS
                remote_fields = {
                    key: root for key, root in oid_map.items()
                    if key.startswith("remote_") or key in {"native_vlan", "duplex"}
                }
                walks = {
                    key: client.bulk_walk(
                        root, max_rows=settings.topology_neighbor_maximum_per_target,
                        max_duration=settings.topology_neighbor_maximum_duration_seconds,
                        cancelled=cancelled,
                    )
                    for key, root in remote_fields.items()
                }
                output[protocol] = tabular_walks(walks, remote_fields, protocol)
            return output
        finally:
            client.close()

    def _source_node(self, topology, target, actor):
        node = self.db.scalar(select(TopologyNode).where(
            TopologyNode.topology_id == topology.id,
            or_(TopologyNode.snmp_target_id == target.id, TopologyNode.device_id == target.device_id)
            if target.device_id else TopologyNode.snmp_target_id == target.id,
        ))
        if not node:
            node = TopologyNode(
                topology_id=topology.id, snmp_target_id=target.id,
                label=target.name, management_ip=target.ip_address,
                node_type="network_device", status="provisional",
                source_type="SNMP", confidence_score=85, is_manual=False,
                created_by=actor.id, updated_by=actor.id,
                metadata_json={"provisional": True, "source_target_id": str(target.id)},
            )
            self.db.add(node)
            self.db.flush()
        return node

    def _interface(self, target_id, neighbor):
        query = select(SNMPInterface).where(SNMPInterface.target_id == target_id)
        if neighbor.local_ifindex is not None:
            return self.db.scalar(query.where(SNMPInterface.interface_index == neighbor.local_ifindex))
        value = neighbor.local_port_identifier
        matches = self.db.scalars(query.where(or_(
            SNMPInterface.name == value, SNMPInterface.description == value,
            SNMPInterface.alias == value,
        ))).all()
        return matches[0] if len(matches) == 1 else None

    def _match(self, topology_id, neighbor):
        target = None
        if neighbor.remote_management_address:
            target = self.db.scalar(select(SNMPTarget).where(
                SNMPTarget.ip_address == neighbor.remote_management_address
            ))
        node = None
        if target:
            node = self.db.scalar(select(TopologyNode).where(
                TopologyNode.topology_id == topology_id,
                or_(TopologyNode.snmp_target_id == target.id, TopologyNode.device_id == target.device_id)
                if target.device_id else TopologyNode.snmp_target_id == target.id,
            ))
        if not node and neighbor.remote_management_address:
            node = self.db.scalar(select(TopologyNode).where(
                TopologyNode.topology_id == topology_id,
                TopologyNode.management_ip == neighbor.remote_management_address,
            ))
        device = self.db.scalar(select(Device).where(Device.ip_address == neighbor.remote_management_address)) if neighbor.remote_management_address else None
        discovered = self.db.scalar(select(DiscoveredDevice).where(
            DiscoveredDevice.ip_address == neighbor.remote_management_address
        )) if neighbor.remote_management_address else None
        return node, target, device, discovered

    def _score(self, neighbor, local_interface, matched_target, bidirectional=False, conflicts=None):
        parts = {}
        if neighbor.remote_chassis_id:
            parts["chassis_id"] = 35
        if neighbor.remote_management_address:
            parts["management_address"] = 20
        if neighbor.remote_system_name:
            parts["system_name"] = 10
        if neighbor.remote_port_id:
            parts["remote_port"] = 10
        if local_interface:
            parts["local_interface"] = 10
        if matched_target:
            parts["existing_target"] = 10
        if bidirectional:
            parts["bidirectional"] = 20
        if conflicts:
            parts["conflict_penalty"] = -min(30, 10 * len(conflicts))
        return max(0, min(100, sum(parts.values()))), parts

    def _device_type(self, capabilities):
        values = set(capabilities)
        if "router" in values:
            return "router"
        if values & {"bridge", "switch", "transparent_bridge"}:
            return "switch"
        if "wlan_access_point" in values:
            return "access_point"
        if "telephone" in values or "phone" in values:
            return "ip_phone"
        if "host" in values or "station_only" in values:
            return "endpoint"
        return "unknown"

    def _stage(self, topology, target, source_node, run, neighbor, actor, seen):
        local_interface = self._interface(target.id, neighbor)
        matched_node, matched_target, device, discovered = self._match(topology.id, neighbor)
        conflicts = []
        contradictory_observation = self.db.scalar(select(TopologyNeighborObservation.id).where(
            TopologyNeighborObservation.topology_id == topology.id,
            TopologyNeighborObservation.source_target_id == target.id,
            TopologyNeighborObservation.local_port_identifier == neighbor.local_port_identifier,
            TopologyNeighborObservation.remote_identity_key != neighbor.identity_key,
            TopologyNeighborObservation.observation_status.in_(("current", "conflict")),
        ))
        if contradictory_observation:
            conflicts.append("multiple_current_neighbors_on_local_port")
        existing_port_links = self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id,
            TopologyLink.source_interface_id == getattr(local_interface, "id", None),
            TopologyLink.status == "active",
        )).all() if local_interface else []
        if any(link.is_manual and link.is_confirmed for link in existing_port_links):
            conflicts.append("confirmed_manual_link_precedence")
        reverse = bool(matched_target and self.db.scalar(select(TopologyNeighborObservation.id).where(
            TopologyNeighborObservation.topology_id == topology.id,
            TopologyNeighborObservation.source_target_id == matched_target.id,
            TopologyNeighborObservation.remote_management_address == target.ip_address,
            TopologyNeighborObservation.observation_status == "current",
        )))
        score, breakdown = self._score(neighbor, local_interface, matched_target, reverse, conflicts)
        observation = self.db.scalar(select(TopologyNeighborObservation).where(
            TopologyNeighborObservation.topology_id == topology.id,
            TopologyNeighborObservation.source_target_id == target.id,
            TopologyNeighborObservation.protocol == neighbor.protocol,
            TopologyNeighborObservation.local_port_identifier == neighbor.local_port_identifier,
            TopologyNeighborObservation.remote_identity_key == neighbor.identity_key,
        ))
        restored = observation and observation.observation_status in {"missing", "stale"}
        if not observation:
            observation = TopologyNeighborObservation(
                topology_id=topology.id, source_target_id=target.id,
                protocol=neighbor.protocol,
                local_port_identifier=neighbor.local_port_identifier,
                remote_identity_key=neighbor.identity_key,
            )
            self.db.add(observation)
        observation.collection_run_id = run.id
        observation.source_device_id = target.device_id
        observation.source_node_id = source_node.id
        observation.source_interface_id = getattr(local_interface, "id", None)
        for field in (
            "local_port_description", "remote_chassis_id", "remote_chassis_subtype",
            "remote_port_id", "remote_port_subtype", "remote_port_description",
            "remote_system_name", "remote_system_description",
            "remote_management_address", "remote_capabilities", "remote_platform",
            "native_vlan", "duplex", "raw_index",
        ):
            setattr(observation, field, getattr(neighbor, field))
        observation.last_seen_at = datetime.now(timezone.utc)
        observation.observation_status = "conflict" if conflicts else "current"
        observation.missing_collections = 0
        observation.normalized_identity = {
            "identity_key": neighbor.identity_key, "protocol": neighbor.protocol,
            "score": score, "warnings": neighbor.warnings,
        }
        observation.metadata_json = {"bidirectional": reverse, "score_breakdown": breakdown}
        self.db.flush()
        seen.add(observation.id)

        candidate = self.db.scalar(select(TopologyNeighborCandidate).where(
            TopologyNeighborCandidate.topology_id == topology.id,
            TopologyNeighborCandidate.remote_identity_key == neighbor.identity_key,
        ))
        if candidate and not matched_node and candidate.matched_topology_node_id:
            matched_node = self.db.get(TopologyNode, candidate.matched_topology_node_id)
        candidate_created = candidate is None
        if candidate_created:
            candidate = TopologyNeighborCandidate(
                topology_id=topology.id, remote_identity_key=neighbor.identity_key
            )
            self.db.add(candidate)
        candidate.source_observation_id = observation.id
        candidate.remote_chassis_id = neighbor.remote_chassis_id
        candidate.remote_system_name = neighbor.remote_system_name
        candidate.remote_management_address = neighbor.remote_management_address
        candidate.remote_port_id = neighbor.remote_port_id
        candidate.device_type_guess = self._device_type(neighbor.remote_capabilities)
        candidate.matched_device_id = getattr(device, "id", None) or getattr(matched_target, "device_id", None)
        candidate.matched_discovered_device_id = getattr(discovered, "id", None) or getattr(matched_target, "discovered_device_id", None)
        candidate.matched_snmp_target_id = getattr(matched_target, "id", None)
        candidate.matched_topology_node_id = getattr(matched_node, "id", None)
        candidate.confidence_score = score
        candidate.score_breakdown = breakdown
        candidate.evidence = {"protocol": neighbor.protocol, "bidirectional": reverse}
        candidate.conflict_flags = conflicts
        candidate.review_status = "conflict" if conflicts else "matched" if matched_node else "unresolved"

        target_node = matched_node
        if not target_node:
            target_node = TopologyNode(
                topology_id=topology.id,
                device_id=getattr(device, "id", None) if not matched_target else None,
                discovered_device_id=getattr(discovered, "id", None) if not device and not matched_target else None,
                snmp_target_id=getattr(matched_target, "id", None),
                label=neighbor.remote_system_name or neighbor.remote_management_address or "Unresolved neighbor",
                description=neighbor.remote_system_description,
                management_ip=neighbor.remote_management_address,
                node_type=candidate.device_type_guess, status="provisional",
                source_type=neighbor.protocol.upper(), confidence_score=score,
                is_manual=False, created_by=actor.id, updated_by=actor.id,
                metadata_json={"provisional": True, "remote_identity_key": neighbor.identity_key},
            )
            self.db.add(target_node)
            self.db.flush()
            candidate.matched_topology_node_id = target_node.id
            run.candidate_nodes_created += 1
            create_audit_log(self.db, actor.username, "TOPOLOGY_NEIGHBOR_CANDIDATE_NODE_CREATED", "TopologyNode", str(target_node.id), "Created an unconfirmed topology-only neighbor node.")
            manager.broadcast_from_thread({"type": "topology_neighbor_candidate_created", "topology_id": str(topology.id), "candidate_id": str(candidate.id), "node_id": str(target_node.id)})

        link = None
        for existing in self.db.scalars(select(TopologyLink).where(
            TopologyLink.topology_id == topology.id,
            or_(
                and_(TopologyLink.source_node_id == source_node.id, TopologyLink.target_node_id == target_node.id),
                and_(TopologyLink.source_node_id == target_node.id, TopologyLink.target_node_id == source_node.id),
            ),
        )).all():
            if existing.is_manual and existing.is_confirmed and conflicts:
                continue
            link = existing
            break
        if not link:
            link = TopologyLink(
                topology_id=topology.id, source_node_id=source_node.id,
                target_node_id=target_node.id, source_interface_id=getattr(local_interface, "id", None),
                link_type="physical", direction="bidirectional" if reverse else "unknown",
                status="unknown" if conflicts else "active",
                source_type=neighbor.protocol.upper(), discovery_method=neighbor.protocol.upper(),
                confidence_score=score, is_manual=False, is_confirmed=False,
                created_by=actor.id, updated_by=actor.id,
                metadata_json={"provisional": True, "conflicts": conflicts},
            )
            self.db.add(link)
            self.db.flush()
            run.candidate_links_created += 1
            create_audit_log(self.db, actor.username, "TOPOLOGY_CANDIDATE_LINK_CREATED", "TopologyLink", str(link.id), "Created an unconfirmed protocol-discovered topology link.")
            manager.broadcast_from_thread({"type": "topology_candidate_link_created", "topology_id": str(topology.id), "link_id": str(link.id), "protocol": neighbor.protocol})
        else:
            link.last_seen_at = datetime.now(timezone.utc)
            link.confidence_score = max(link.confidence_score, score)
            run.candidate_links_updated += 1
            manager.broadcast_from_thread({"type": "topology_candidate_link_updated", "topology_id": str(topology.id), "link_id": str(link.id), "protocol": neighbor.protocol})
        self.db.add(TopologyLinkEvidence(
            topology_link_id=link.id, source_type=neighbor.protocol.upper(),
            source_reference=str(observation.id),
            evidence_type="bidirectional_neighbor" if reverse else "unidirectional_neighbor",
            evidence_value=f"{neighbor.local_port_identifier} -> {neighbor.remote_port_id or 'unresolved'}"[:500],
            confidence_score=score,
        ))
        if restored:
            self.db.add(TopologyChange(
                topology_id=topology.id, change_type="neighbor_restored",
                entity_type="link", link_id=link.id, source_type=neighbor.protocol.upper(),
                confidence_score=score, current_values={"observation_id": str(observation.id)},
            ))
            manager.broadcast_from_thread({"type": "topology_link_restored", "topology_id": str(topology.id), "link_id": str(link.id)})
        run.conflicts += bool(conflicts)
        if conflicts:
            manager.broadcast_from_thread({"type": "topology_neighbor_conflict_detected", "topology_id": str(topology.id), "candidate_id": str(candidate.id), "conflict_count": len(conflicts)})

    def _age_missing(self, topology, target, run, seen):
        previous = self.db.scalars(select(TopologyNeighborObservation).where(
            TopologyNeighborObservation.topology_id == topology.id,
            TopologyNeighborObservation.source_target_id == target.id,
            TopologyNeighborObservation.id.not_in(seen) if seen else True,
            TopologyNeighborObservation.observation_status.in_(("current", "stale")),
        )).all()
        for observation in previous:
            observation.missing_collections += 1
            if observation.missing_collections >= settings.topology_neighbor_missing_grace_collections:
                observation.observation_status = "missing"
            else:
                observation.observation_status = "stale"

    def collect(self, topology, target, mode, dry_run, actor):
        if not topology.enabled:
            raise HTTPException(409, "Topology is disabled.")
        if not target or not target.enabled:
            raise HTTPException(409, "SNMP target is unavailable or disabled.")
        protocols = self.protocols(target, mode)
        if "lldp" in protocols and not settings.topology_lldp_collection_enabled:
            raise HTTPException(409, "LLDP collection is disabled.")
        if "cdp" in protocols and not settings.topology_cdp_collection_enabled:
            raise HTTPException(409, "CDP collection is disabled.")
        run = TopologyNeighborCollectionRun(
            topology_id=topology.id, target_id=target.id,
            protocols_requested=protocols, triggered_by=actor.id, dry_run=dry_run,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        run.status = "running"
        started = monotonic()
        manager.broadcast_from_thread({"type": "topology_neighbor_collection_started", "topology_id": str(topology.id), "run_id": str(run.id)})
        create_audit_log(self.db, actor.username, "TOPOLOGY_NEIGHBOR_COLLECTION_STARTED", "TopologyNeighborCollectionRun", str(run.id), f"Started bounded {','.join(protocols)} neighbor collection.")
        try:
            with snmp_operation_lock(target.id, target.credential_id):
                rows_by_protocol = (
                    self.collector(target, protocols, lambda: run.cancellation_requested)
                    if self.collector else self._live_rows(target, protocols, lambda: run.cancellation_requested)
                )
                normalized = []
                warnings = []
                for protocol in protocols:
                    rows = rows_by_protocol.get(protocol, [])
                    run.raw_neighbors_seen += len(rows)
                    parser = parse_lldp_rows if protocol == "lldp" else parse_cdp_rows
                    values, parser_warnings = parser(rows, settings.topology_neighbor_maximum_per_target)
                    normalized.extend(values)
                    warnings.extend(parser_warnings)
                    run.protocols_completed.append(protocol)
                run.normalized_neighbors = len(normalized)
                run.local_ports_seen = len({item.local_port_identifier for item in normalized})
                if run.cancellation_requested:
                    raise SNMPClientError("cancelled", "Neighbor collection was cancelled.")
                if dry_run:
                    run.status = "completed"
                    run.error_summary = "; ".join(warnings)[:500] or None
                else:
                    source_node = self._source_node(topology, target, actor)
                    seen = set()
                    for neighbor in normalized:
                        self._stage(topology, target, source_node, run, neighbor, actor, seen)
                    self._age_missing(topology, target, run, seen)
                    run.status = "partial" if warnings else "completed"
                    run.errors_count = len(warnings)
                    run.error_summary = "; ".join(warnings)[:500] or None
            create_audit_log(self.db, actor.username, f"TOPOLOGY_NEIGHBOR_COLLECTION_{run.status.upper()}", "TopologyNeighborCollectionRun", str(run.id), f"Neighbor collection ended {run.status}; {run.normalized_neighbors} normalized neighbors.")
        except SNMPClientError as error:
            self.db.rollback()
            run = self.db.get(TopologyNeighborCollectionRun, run.id)
            run.status = "cancelled" if error.category == "cancelled" else "failed"
            run.error_category = error.category
            run.error_summary = error.safe_message[:500]
            run.errors_count += 1
        except Exception:
            self.db.rollback()
            run = self.db.get(TopologyNeighborCollectionRun, run.id)
            run.status = "failed"
            run.error_category = "unknown_error"
            run.error_summary = "Neighbor collection failed safely."
            run.errors_count += 1
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = int((monotonic() - started) * 1000)
        if run.status in {"failed", "cancelled"}:
            create_audit_log(self.db, actor.username, f"TOPOLOGY_NEIGHBOR_COLLECTION_{run.status.upper()}", "TopologyNeighborCollectionRun", str(run.id), f"Neighbor collection ended {run.status} ({run.error_category or 'cancelled'}).")
        if run.status == "failed":
            notify_snmp(self.db, "HIOP topology neighbor collection failed", f"Neighbor run {run.id} for target {target.id} failed with {run.error_category or 'unknown_error'}.")
        self.db.commit()
        self.db.refresh(run)
        manager.broadcast_from_thread({
            "type": f"topology_neighbor_collection_{run.status}",
            "topology_id": str(topology.id), "run_id": str(run.id),
            "status": run.status, "normalized_neighbors": run.normalized_neighbors,
        })
        return run
