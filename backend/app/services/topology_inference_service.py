"""Explainable topology inference with administrator-owned risky decisions."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.models.topology import (
    DeviceDependency, Topology, TopologyChange, TopologyLink,
    TopologyLinkEvidence, TopologyNode, TopologyNodeSegment, TopologySnapshot,
    TopologySnapshotLink, TopologySnapshotNode,
)
from app.models.topology_inference import (
    TopologyConfidenceHistory, TopologyConflict, TopologyInferenceRun,
    TopologyReviewItem,
)
from app.services.audit_service import create_audit_log
from app.services.topology_service import TopologyService
from app.websocket.connection_manager import manager

LAYER_RANK = {"external": 6, "core": 5, "distribution": 4, "access": 3, "service": 2, "endpoint": 1, "unknown": 0}


class TopologyInferenceService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def graph_checksum(nodes, links) -> str:
        payload = {
            "nodes": sorted((str(n.id), str(n.device_id or ""), str(n.snmp_target_id or ""), n.layer, n.status) for n in nodes),
            "links": sorted((str(l.id), *sorted((str(l.source_node_id), str(l.target_node_id))), l.status, l.confidence_score) for l in links),
        }
        return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def link_key(link):
        endpoints = tuple(sorted((str(link.source_node_id), str(link.target_node_id))))
        interfaces = tuple(sorted(str(value or "") for value in (link.source_interface_id, link.target_interface_id)))
        return endpoints + interfaces

    @staticmethod
    def recalculate_confidence(link, evidence, nodes_by_id, now=None, segments_by_node=None):
        now = now or datetime.now(timezone.utc)
        contributions = {"base_neighbor_evidence": 25}
        sources = {item.source_type.upper() for item in evidence}
        types = {item.evidence_type for item in evidence}
        if link.is_manual and link.is_confirmed:
            contributions["confirmed_manual"] = 75
        if "bidirectional_neighbor" in types:
            contributions["bidirectional"] = 25
        if {"LLDP", "CDP"} <= sources:
            contributions["protocol_agreement"] = 15
        if link.source_interface_id and link.target_interface_id:
            contributions["both_interfaces_resolved"] = 15
        elif link.source_interface_id or link.target_interface_id:
            contributions["one_interface_resolved"] = 7
        source, target = nodes_by_id.get(link.source_node_id), nodes_by_id.get(link.target_node_id)
        if source and target and (source.device_id or source.snmp_target_id) and (target.device_id or target.snmp_target_id):
            contributions["linked_inventory_or_target"] = 10
        segments_by_node = segments_by_node or {}
        shared_segments = set(segments_by_node.get(link.source_node_id, set())) & set(segments_by_node.get(link.target_node_id, set()))
        if shared_segments:
            contributions["shared_network_segment"] = 5
        age_days = max(0, (now - link.first_seen_at).days) if link.first_seen_at else 0
        if age_days >= 30 and link.status == "active":
            contributions["historical_stability"] = 5
        if link.status == "missing":
            contributions["missing_penalty"] = -30
        if (link.metadata_json or {}).get("conflicts"):
            contributions["conflict_penalty"] = -20
        return max(0, min(100, sum(contributions.values()))), contributions

    @staticmethod
    def infer_layer(node, degree):
        if node.layer != "unknown" and node.layer:
            return node.layer, 100 if node.is_manual else 85, {"existing_layer": node.layer}
        kind = (node.node_type or "").lower()
        role = (node.role or "").lower()
        if kind in {"printer", "endpoint", "ip_phone", "computer"}:
            return "endpoint", 85, {"device_type": kind}
        if kind in {"access_point", "wireless_access_point"}:
            return "access", 80, {"device_type": kind}
        if kind in {"server", "service", "controller"}:
            return "service", 75, {"device_type": kind}
        if kind in {"internet", "external_network"}:
            return "external", 95, {"device_type": kind}
        if "core" in role or "core" in node.label.lower():
            return "core", 85, {"role_or_name": "core"}
        if "distribution" in role or "dist" in node.label.lower():
            return "distribution", 75, {"role_or_name": "distribution"}
        if kind in {"switch", "router", "network_device"}:
            if degree >= 12:
                return "distribution", 65, {"interface_degree": degree}
            return "access", 65, {"device_type": kind, "interface_degree": degree}
        return "unknown", 0, {}

    @staticmethod
    def classify_link(source_layer, target_layer, vlan_id=None, source_name="", target_name=""):
        if "wireless" in (source_name + target_name).lower():
            return "wireless", 70
        if vlan_id is not None:
            return "trunk", 70
        source_rank, target_rank = LAYER_RANK.get(source_layer, 0), LAYER_RANK.get(target_layer, 0)
        if source_rank > target_rank:
            return "downlink", 70
        if target_rank > source_rank:
            return "uplink", 70
        if source_layer == target_layer == "endpoint":
            return "access", 55
        return "unknown", 30

    @staticmethod
    def reconstruct_paths(source_id, target_id, links, dependencies=(), path_type="any", max_depth=20, max_paths=5):
        graph = defaultdict(list)
        if path_type in {"physical", "layer_aware", "any"}:
            for link in links:
                if link.status not in {"active", "unknown"} or link.is_suppressed:
                    continue
                graph[link.source_node_id].append((link.target_node_id, "physical", link.id))
                graph[link.target_node_id].append((link.source_node_id, "physical", link.id))
        if path_type in {"dependency", "any"}:
            for dependency in dependencies:
                if not dependency.enabled:
                    continue
                graph[dependency.upstream_node_id].append((dependency.downstream_node_id, "dependency", dependency.id))
                graph[dependency.downstream_node_id].append((dependency.upstream_node_id, "dependency", dependency.id))
        queue = deque([(source_id, [source_id], [])])
        paths = []
        while queue and len(paths) < max_paths:
            current, nodes, edges = queue.popleft()
            if len(edges) >= max_depth:
                continue
            for neighbor, edge_type, edge_id in graph[current]:
                if neighbor in nodes:
                    continue
                next_nodes, next_edges = nodes + [neighbor], edges + [{"id": str(edge_id), "type": edge_type}]
                if neighbor == target_id:
                    paths.append({"nodes": [str(value) for value in next_nodes], "edges": next_edges, "hops": len(next_edges)})
                else:
                    queue.append((neighbor, next_nodes, next_edges))
        return sorted(paths, key=lambda item: item["hops"])

    def _review(self, topology_id, run, review_type, entity_type, entity_id, key, proposed, evidence, impact, confidence):
        existing = self.db.scalar(select(TopologyReviewItem).where(
            TopologyReviewItem.topology_id == topology_id,
            TopologyReviewItem.dedupe_key == key,
            TopologyReviewItem.status == "pending",
        ))
        if existing:
            existing.inference_run_id = run.id
            existing.proposed_change = proposed
            existing.evidence = evidence
            existing.impact = impact
            existing.confidence_score = confidence
            return existing, False
        item = TopologyReviewItem(
            topology_id=topology_id, inference_run_id=run.id,
            review_type=review_type, entity_type=entity_type, entity_id=entity_id,
            dedupe_key=key, proposed_change=proposed, evidence=evidence,
            impact=impact, confidence_score=confidence,
        )
        self.db.add(item)
        self.db.flush()
        manager.broadcast_from_thread({"type": "topology_review_created", "topology_id": str(topology_id), "review_item_id": str(item.id), "review_type": review_type})
        return item, True

    def _conflict(self, topology_id, run, kind, severity, entity_type, entity_id, related, evidence, resolution, confidence=50):
        conflict = TopologyConflict(
            topology_id=topology_id, inference_run_id=run.id,
            conflict_type=kind, severity=severity, entity_type=entity_type,
            entity_id=entity_id, related_entity_ids=[str(value) for value in related],
            confidence_score=confidence, evidence=evidence,
            suggested_resolution=resolution,
        )
        self.db.add(conflict)
        run.conflicts_detected += 1
        manager.broadcast_from_thread({"type": "topology_conflict_detected", "topology_id": str(topology_id), "conflict_type": kind, "severity": severity})
        return conflict

    def _merge_links(self, topology, run, links, actor):
        groups = defaultdict(list)
        for link in links:
            if link.link_type == "physical" and not link.is_suppressed:
                groups[self.link_key(link)].append(link)
        for group in groups.values():
            if len(group) < 2:
                continue
            manuals = [link for link in group if link.is_manual and link.is_confirmed]
            if len(manuals) > 1:
                self._conflict(topology.id, run, "duplicate_confirmed_manual_links", "high", "link", manuals[0].id, [link.id for link in manuals[1:]], {}, "Administrator must choose the authoritative manual link.", 90)
                continue
            canonical = sorted(group, key=lambda link: (link.is_manual and link.is_confirmed, link.is_confirmed, link.confidence_score), reverse=True)[0]
            for duplicate in group:
                if duplicate.id == canonical.id or (duplicate.is_manual and duplicate.is_confirmed):
                    continue
                evidence = self.db.scalars(select(TopologyLinkEvidence).where(
                    TopologyLinkEvidence.topology_link_id == duplicate.id
                )).all()
                for item in evidence:
                    item.topology_link_id = canonical.id
                canonical.first_seen_at = min(canonical.first_seen_at, duplicate.first_seen_at)
                canonical.last_seen_at = max(canonical.last_seen_at, duplicate.last_seen_at)
                canonical.metadata_json = {
                    **(canonical.metadata_json or {}),
                    "merged_link_ids": sorted(set((canonical.metadata_json or {}).get("merged_link_ids", []) + [str(duplicate.id)])),
                }
                duplicate.status = "inactive"
                duplicate.is_suppressed = True
                duplicate.metadata_json = {**(duplicate.metadata_json or {}), "merged_into": str(canonical.id)}
                run.links_merged += 1
                self.db.add(TopologyChange(
                    topology_id=topology.id, change_type="duplicate_link_merged",
                    entity_type="link", link_id=canonical.id, source_type="inferred",
                    confidence_score=canonical.confidence_score,
                    previous_values={"duplicate_link_id": str(duplicate.id)},
                    current_values={"canonical_link_id": str(canonical.id)},
                ))
                create_audit_log(self.db, actor.username, "TOPOLOGY_LINK_MERGED", "TopologyLink", str(canonical.id), f"Merged provisional link {duplicate.id} into the canonical relationship.")

    def _node_recommendations(self, topology, run, nodes):
        groups = defaultdict(list)
        for node in nodes:
            if node.management_ip:
                groups[f"ip:{node.management_ip}"].append(node)
            identity = (node.metadata_json or {}).get("remote_identity_key")
            if identity:
                groups[f"identity:{identity}"].append(node)
        seen = set()
        for key, group in groups.items():
            unique = {node.id: node for node in group}
            if len(unique) < 2:
                continue
            signature = tuple(sorted(str(value) for value in unique))
            if signature in seen:
                continue
            seen.add(signature)
            official = [node for node in unique.values() if node.device_id]
            canonical = official[0] if len(official) == 1 else sorted(unique.values(), key=lambda node: (node.is_manual, node.confidence_score), reverse=True)[0]
            duplicates = [node for node in unique.values() if node.id != canonical.id]
            _, created = self._review(
                topology.id, run, "merge_nodes", "node", canonical.id,
                f"merge-nodes:{':'.join(signature)}",
                {"canonical_node_id": str(canonical.id), "duplicate_node_ids": [str(node.id) for node in duplicates]},
                {"identity_key": key, "official_nodes": [str(node.id) for node in official]},
                {"links_to_rewire": sum(1 for node in duplicates for _ in [node])},
                90 if key.startswith("identity:") else 75,
            )
            run.node_recommendations += created

    def _detect_conflicts(self, topology, run, nodes, links):
        by_interface = defaultdict(list)
        for link in links:
            if link.status == "active" and not link.is_suppressed:
                for interface_id in (link.source_interface_id, link.target_interface_id):
                    if interface_id:
                        by_interface[interface_id].append(link)
        for interface_id, peers in by_interface.items():
            endpoint_pairs = {tuple(sorted((str(link.source_node_id), str(link.target_node_id)))) for link in peers}
            if len(endpoint_pairs) > 1:
                self._conflict(topology.id, run, "interface_multiple_active_peers", "high", "interface", interface_id, [link.id for link in peers], {"peer_count": len(endpoint_pairs)}, "Review interface ownership and suppress incorrect provisional links.", 95)
        by_ip = defaultdict(list)
        for node in nodes:
            if node.management_ip:
                by_ip[node.management_ip].append(node)
        for address, matches in by_ip.items():
            if len(matches) > 1:
                vendors = sorted({node.vendor for node in matches if getattr(node, "vendor", None)})
                evidence = {"management_ip": address, "vendors": vendors}
                self._conflict(topology.id, run, "management_ip_multiple_nodes", "high" if len(vendors) > 1 else "medium", "node", matches[0].id, [node.id for node in matches[1:]], evidence, "Review the duplicate-node recommendation; do not merge official inventory identities automatically.", 80)
        for link in links:
            if not link.is_manual and (link.metadata_json or {}).get("conflicts"):
                self._conflict(topology.id, run, "manual_inferred_disagreement", "high", "link", link.id, [], {"flags": link.metadata_json["conflicts"]}, "Preserve the confirmed manual link and review protocol evidence.", link.confidence_score)

    def _layers_and_dependencies(self, topology, run, nodes, links, include_dependencies, include_layers):
        degree = defaultdict(int)
        for link in links:
            if link.status == "active" and not link.is_suppressed:
                degree[link.source_node_id] += 1
                degree[link.target_node_id] += 1
        layers = {}
        for node in nodes:
            layer, confidence, evidence = self.infer_layer(node, degree[node.id])
            layers[node.id] = layer
            if include_layers and node.layer == "unknown" and layer != "unknown":
                if not node.is_manual and confidence >= settings.topology_inference_review_threshold:
                    node.layer = layer
                    node.metadata_json = {**(node.metadata_json or {}), "inferred_layer": {"confidence": confidence, "evidence": evidence}}
                else:
                    _, created = self._review(
                        topology.id, run, "assign_layer", "node", node.id,
                        f"assign-layer:{node.id}:{layer}",
                        {"node_id": str(node.id), "layer": layer},
                        evidence, {"path_classification_may_change": True}, confidence,
                    )
                    run.review_items_created += created
        for link in links:
            source, target = next((node for node in nodes if node.id == link.source_node_id), None), next((node for node in nodes if node.id == link.target_node_id), None)
            classification, confidence = self.classify_link(
                layers.get(link.source_node_id, "unknown"),
                layers.get(link.target_node_id, "unknown"),
                link.vlan_id, getattr(source, "label", ""), getattr(target, "label", ""),
            )
            link.metadata_json = {
                **(link.metadata_json or {}),
                "inferred_link_classification": {
                    "value": classification, "confidence": confidence,
                    "source_layer": layers.get(link.source_node_id, "unknown"),
                    "target_layer": layers.get(link.target_node_id, "unknown"),
                },
            }
        if not include_dependencies:
            return
        graph_service = TopologyService(self.db)
        for link in links:
            if link.status != "active" or link.is_suppressed:
                continue
            source_layer, target_layer = layers.get(link.source_node_id, "unknown"), layers.get(link.target_node_id, "unknown")
            source_rank, target_rank = LAYER_RANK.get(source_layer, 0), LAYER_RANK.get(target_layer, 0)
            if source_rank == target_rank or min(source_rank, target_rank) == 0:
                continue
            upstream, downstream = (link.source_node_id, link.target_node_id) if source_rank > target_rank else (link.target_node_id, link.source_node_id)
            exists = self.db.scalar(select(DeviceDependency).where(
                DeviceDependency.topology_id == topology.id,
                DeviceDependency.upstream_node_id == upstream,
                DeviceDependency.downstream_node_id == downstream,
                DeviceDependency.dependency_type == "network",
            ))
            if exists or graph_service._dependency_reachable(topology.id, downstream, upstream):
                continue
            confidence = min(90, max(60, link.confidence_score))
            if confidence >= settings.topology_inference_dependency_threshold:
                self.db.add(DeviceDependency(
                    topology_id=topology.id, upstream_node_id=upstream,
                    downstream_node_id=downstream, dependency_type="network",
                    criticality="medium", source_type="inferred",
                    confidence_score=confidence, is_manual=False,
                    description=f"Inferred from {source_layer}/{target_layer} physical hierarchy.",
                ))
                run.dependencies_inferred += 1
            else:
                _, created = self._review(
                    topology.id, run, "create_dependency", "link", link.id,
                    f"dependency:{upstream}:{downstream}",
                    {"upstream_node_id": str(upstream), "downstream_node_id": str(downstream), "dependency_type": "network"},
                    {"link_id": str(link.id), "layers": [source_layer, target_layer]},
                    {"dependency_graph_changes": True}, confidence,
                )
                run.review_items_created += created

    def run(self, topology: Topology, payload, actor):
        if not topology.enabled:
            raise HTTPException(409, "Topology is disabled.")
        nodes = self.db.scalars(select(TopologyNode).where(TopologyNode.topology_id == topology.id)).all()
        links = self.db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology.id)).all()
        if len(nodes) > settings.topology_inference_maximum_nodes or len(links) > settings.topology_inference_maximum_links:
            raise HTTPException(413, "Topology exceeds configured inference limits.")
        active = self.db.scalar(select(TopologyInferenceRun).where(
            TopologyInferenceRun.topology_id == topology.id,
            TopologyInferenceRun.status.in_(("pending", "running")),
        ))
        if active:
            raise HTTPException(409, "Topology already has an active inference run.")
        run = TopologyInferenceRun(
            topology_id=topology.id, status="running", triggered_by=actor.id,
            dry_run=payload.dry_run, nodes_analyzed=len(nodes), links_analyzed=len(links),
            graph_checksum_before=self.graph_checksum(nodes, links),
        )
        self.db.add(run)
        self.db.flush()
        started = monotonic()
        create_audit_log(self.db, actor.username, "TOPOLOGY_INFERENCE_STARTED", "TopologyInferenceRun", str(run.id), "Started bounded topology inference.")
        manager.broadcast_from_thread({"type": "topology_inference_started", "topology_id": str(topology.id), "run_id": str(run.id)})
        self.db.commit()
        self.db.refresh(run)
        run_id = run.id
        try:
            nodes_by_id = {node.id: node for node in nodes}
            memberships = self.db.scalars(select(TopologyNodeSegment).where(
                TopologyNodeSegment.topology_node_id.in_(nodes_by_id)
            )).all() if nodes_by_id else []
            segments_by_node = defaultdict(set)
            for membership in memberships:
                segments_by_node[membership.topology_node_id].add(membership.network_segment_id)
            for link in links:
                evidence = self.db.scalars(select(TopologyLinkEvidence).where(
                    TopologyLinkEvidence.topology_link_id == link.id
                )).all()
                score, contributions = self.recalculate_confidence(
                    link, evidence, nodes_by_id, segments_by_node=segments_by_node
                )
                self.db.add(TopologyConfidenceHistory(
                    topology_id=topology.id, inference_run_id=run.id,
                    entity_type="link", entity_id=link.id,
                    previous_score=link.confidence_score, calculated_score=score,
                    contributions=contributions,
                ))
                if not payload.dry_run:
                    link.confidence_score = score
                    link.metadata_json = {
                        **(link.metadata_json or {}),
                        "confidence_contributions": contributions,
                        "evidence_sources": sorted({item.source_type for item in evidence}),
                        "confidence_calculated_at": datetime.now(timezone.utc).isoformat(),
                    }
            self._detect_conflicts(topology, run, nodes, links)
            self._node_recommendations(topology, run, nodes)
            if not payload.dry_run:
                self._merge_links(topology, run, links, actor)
                self._layers_and_dependencies(topology, run, nodes, links, payload.include_dependencies, payload.include_layer_suggestions)
            run.review_items_created += run.node_recommendations
            if run.conflicts_detected:
                create_audit_log(self.db, actor.username, "TOPOLOGY_CONFLICT_DETECTED", "TopologyInferenceRun", str(run.id), f"Detected {run.conflicts_detected} topology conflicts requiring review.")
            run.status = "completed"
            run.summary = {
                "manual_links_preserved": sum(link.is_manual and link.is_confirmed for link in links),
                "orphan_nodes": len(self.orphan_analysis(nodes, links)["orphan_node_ids"]),
                "dry_run": payload.dry_run,
            }
            self.db.flush()
            refreshed_links = self.db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology.id)).all()
            run.graph_checksum_after = self.graph_checksum(nodes, refreshed_links)
            create_audit_log(self.db, actor.username, "TOPOLOGY_INFERENCE_COMPLETED", "TopologyInferenceRun", str(run.id), f"Inference completed with {run.links_merged} link merges and {run.conflicts_detected} conflicts.")
        except Exception:
            self.db.rollback()
            run = self.db.get(TopologyInferenceRun, run_id)
            if run is None:
                raise
            run.status = "failed"
            run.error_summary = "Topology inference failed safely."
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = int((monotonic() - started) * 1000)
        self.db.commit()
        self.db.refresh(run)
        manager.broadcast_from_thread({"type": "topology_inference_completed", "topology_id": str(topology.id), "run_id": str(run.id), "status": run.status, "conflicts": run.conflicts_detected})
        if run.status == "completed" and not payload.dry_run:
            manager.broadcast_from_thread({"type": "topology_graph_updated", "topology_id": str(topology.id), "run_id": str(run.id)})
        return run

    @staticmethod
    def orphan_analysis(nodes, links):
        adjacency = defaultdict(set)
        for link in links:
            if link.status == "active" and not link.is_suppressed:
                adjacency[link.source_node_id].add(link.target_node_id)
                adjacency[link.target_node_id].add(link.source_node_id)
        orphans = [str(node.id) for node in nodes if not adjacency[node.id] and node.node_type not in {"internet", "external_network"}]
        islands, visited = [], set()
        for node in nodes:
            if node.id in visited:
                continue
            queue, component = [node.id], []
            visited.add(node.id)
            while queue:
                current = queue.pop()
                component.append(str(current))
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(component) > 1:
                islands.append(component)
        missing_uplinks = [str(node.id) for node in nodes if node.layer in {"access", "distribution"} and not any(LAYER_RANK.get(getattr(next((n for n in nodes if n.id == peer), None), "layer", "unknown"), 0) > LAYER_RANK.get(node.layer, 0) for peer in adjacency[node.id])]
        return {
            "orphan_node_ids": orphans,
            "isolated_components": islands,
            "missing_uplink_node_ids": missing_uplinks,
            "recommendations": ["Review unresolved neighbor candidates." if orphans else "No unlinked devices detected."],
        }

    def compare_snapshot(self, topology_id, snapshot_id):
        snapshot = self.db.get(TopologySnapshot, snapshot_id)
        if not snapshot or snapshot.topology_id != topology_id:
            raise HTTPException(404, "Topology snapshot was not found.")
        current_nodes = self.db.scalars(select(TopologyNode).where(TopologyNode.topology_id == topology_id)).all()
        current_links = self.db.scalars(select(TopologyLink).where(TopologyLink.topology_id == topology_id)).all()
        old_nodes = self.db.scalars(select(TopologySnapshotNode).where(TopologySnapshotNode.snapshot_id == snapshot_id)).all()
        old_links = self.db.scalars(select(TopologySnapshotLink).where(TopologySnapshotLink.snapshot_id == snapshot_id)).all()
        old_node_map = {row.source_topology_node_id: row for row in old_nodes if row.source_topology_node_id}
        current_node_map = {row.id: row for row in current_nodes}
        old_link_ids = {row.source_topology_link_id for row in old_links if row.source_topology_link_id}
        current_link_ids = {row.id for row in current_links}
        return {
            "added_nodes": [str(value) for value in current_node_map.keys() - old_node_map.keys()],
            "removed_nodes": [str(value) for value in old_node_map.keys() - current_node_map.keys()],
            "added_links": [str(value) for value in current_link_ids - old_link_ids],
            "removed_links": [str(value) for value in old_link_ids - current_link_ids],
            "layer_changes": [
                {"node_id": str(node_id), "before": old_node_map[node_id].layer, "after": current_node_map[node_id].layer}
                for node_id in current_node_map.keys() & old_node_map.keys()
                if current_node_map[node_id].layer != old_node_map[node_id].layer
            ],
            "parent_changes": [
                {"node_id": str(node_id), "before": str(old_node_map[node_id].metadata_json.get("parent_node_id") or ""), "after": str(current_node_map[node_id].parent_node_id or "")}
                for node_id in current_node_map.keys() & old_node_map.keys()
                if str(old_node_map[node_id].metadata_json.get("parent_node_id") or "") != str(current_node_map[node_id].parent_node_id or "")
            ],
        }
