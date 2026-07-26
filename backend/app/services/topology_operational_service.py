"""Bounded topology health, analytics, alerts, change evaluation, and retention."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import StringIO
import csv

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.models.topology import (
    DeviceDependency, Topology, TopologyChange, TopologyLink, TopologyLinkEvidence,
    TopologyNode, TopologySnapshot, TopologySnapshotLink, TopologySnapshotNode,
)
from app.models.topology_inference import TopologyConflict, TopologyInferenceRun
from app.models.topology_neighbor import TopologyNeighborCollectionRun, TopologyNeighborObservation
from app.models.topology_operations import (
    TopologyAlertEvent, TopologyAlertRule, TopologyOperationalRun,
    TopologyScheduleConfiguration,
)
from app.services.audit_service import create_audit_log
from app.services.topology_inference_service import TopologyInferenceService
from app.services.topology_service import TopologyService
from app.websocket.connection_manager import manager


def _safe_csv(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class TopologyOperationalService:
    def __init__(self, db):
        self.db = db

    def schedule(self, topology_id):
        row = self.db.scalar(select(TopologyScheduleConfiguration).where(
            TopologyScheduleConfiguration.topology_id == topology_id
        ))
        if not row:
            row = TopologyScheduleConfiguration(topology_id=topology_id)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row

    def health(self, topology_id):
        topology = self.db.get(Topology, topology_id)
        if not topology:
            raise HTTPException(404, "Topology was not found.")
        schedule = self.schedule(topology_id)
        latest_collection = self.db.scalar(select(TopologyNeighborCollectionRun).where(
            TopologyNeighborCollectionRun.topology_id == topology_id,
            TopologyNeighborCollectionRun.status == "completed",
        ).order_by(TopologyNeighborCollectionRun.completed_at.desc()))
        latest_inference = self.db.scalar(select(TopologyInferenceRun).where(
            TopologyInferenceRun.topology_id == topology_id,
            TopologyInferenceRun.status == "completed",
        ).order_by(TopologyInferenceRun.completed_at.desc()))
        latest_snapshot = self.db.scalar(select(TopologySnapshot).where(
            TopologySnapshot.topology_id == topology_id,
            TopologySnapshot.status == "completed",
        ).order_by(TopologySnapshot.completed_at.desc()))
        stats = TopologyService(self.db)
        component_count = stats.connected_components(topology_id)["count"]
        node_count = self.db.query(TopologyNode).filter_by(topology_id=topology_id, is_hidden=False).count()
        active_links = self.db.query(TopologyLink).filter_by(topology_id=topology_id, status="active", is_suppressed=False).count()
        orphan_count = len(TopologyInferenceService.orphan_analysis(
            self.db.query(TopologyNode).filter_by(topology_id=topology_id).all(),
            self.db.query(TopologyLink).filter_by(topology_id=topology_id).all(),
        )["orphan_node_ids"])
        conflicts = self.db.query(TopologyConflict).filter_by(topology_id=topology_id, status="open").count()
        critical_alerts = self.db.query(TopologyAlertEvent).filter_by(topology_id=topology_id, is_open=True, severity="critical").count()
        freshness_limit = datetime.now(timezone.utc) - timedelta(minutes=schedule.stale_run_timeout_minutes * 2)
        stale = not latest_collection or not latest_collection.completed_at or latest_collection.completed_at < freshness_limit
        if critical_alerts or component_count > 1:
            overall = "critical"
        elif stale or conflicts or orphan_count:
            overall = "degraded"
        else:
            overall = "healthy"
        return {
            "overall_status": overall, "topology_id": str(topology_id),
            "last_successful_neighbor_collection": getattr(latest_collection, "completed_at", None),
            "last_successful_inference": getattr(latest_inference, "completed_at", None),
            "last_snapshot": getattr(latest_snapshot, "completed_at", None),
            "evidence_freshness": "stale" if stale else "fresh",
            "confirmed_link_health": {"active_links": active_links},
            "conflict_count": conflicts, "orphan_count": orphan_count,
            "connected_component_count": component_count, "node_count": node_count,
            "critical_alerts": critical_alerts, "maintenance_mode": schedule.maintenance_mode,
            "maintenance_reason": schedule.maintenance_reason, "stale_topology": stale,
        }

    def analytics(self, topology_id):
        nodes = self.db.query(TopologyNode).filter_by(topology_id=topology_id, is_hidden=False).all()
        links = self.db.query(TopologyLink).filter_by(topology_id=topology_id, status="active", is_suppressed=False).all()
        if len(nodes) > settings.topology_maximum_graph_nodes or len(links) > settings.topology_maximum_graph_links:
            raise HTTPException(413, "Topology exceeds configured analytics bounds.")
        adjacency = defaultdict(set)
        edge_ids = {}
        for link in links:
            if link.confidence_score < 70:
                continue
            adjacency[link.source_node_id].add(link.target_node_id)
            adjacency[link.target_node_id].add(link.source_node_id)
            edge_ids[frozenset((link.source_node_id, link.target_node_id))] = link.id
        articulation, bridges = self._tarjan([node.id for node in nodes], adjacency, edge_ids)
        redundant = [str(node.id) for node in nodes if len(adjacency[node.id]) > 1]
        single_uplink = [str(node.id) for node in nodes if node.layer in {"access", "distribution"} and len(adjacency[node.id]) == 1]
        downstream = defaultdict(int)
        dependencies = self.db.query(DeviceDependency).filter_by(topology_id=topology_id, enabled=True).all()
        for dependency in dependencies:
            downstream[dependency.upstream_node_id] += 1
        return {
            "structural_only": True,
            "articulation_node_ids": [str(value) for value in articulation],
            "bridge_link_ids": [str(value) for value in bridges],
            "nodes_with_multiple_neighbors": redundant,
            "single_uplink_node_ids": single_uplink,
            "high_impact_nodes": [{"node_id": str(key), "downstream_count": value} for key, value in sorted(downstream.items(), key=lambda item: item[1], reverse=True)[:50]],
            "confidence_warning": "Findings exclude provisional links below 70 confidence and are structural, not guaranteed outage predictions.",
        }

    @staticmethod
    def _tarjan(node_ids, adjacency, edge_ids):
        order, low, parent, articulation, bridges = {}, {}, {}, set(), set()
        counter = 0
        def visit(node):
            nonlocal counter
            counter += 1; order[node] = low[node] = counter; children = 0
            for peer in adjacency[node]:
                if peer not in order:
                    parent[peer] = node; children += 1; visit(peer); low[node] = min(low[node], low[peer])
                    if node not in parent and children > 1: articulation.add(node)
                    if node in parent and low[peer] >= order[node]: articulation.add(node)
                    if low[peer] > order[node]: bridges.add(edge_ids[frozenset((node, peer))])
                elif parent.get(node) != peer:
                    low[node] = min(low[node], order[peer])
        for node in node_ids:
            if node not in order: visit(node)
        return articulation, bridges

    def evaluate_changes(self, topology_id, snapshot_id=None, actor="scheduler"):
        snapshot = self.db.get(TopologySnapshot, snapshot_id) if snapshot_id else self.db.scalar(
            select(TopologySnapshot).where(
                TopologySnapshot.topology_id == topology_id,
                TopologySnapshot.status == "completed",
            ).order_by(TopologySnapshot.created_at.desc()).offset(1)
        )
        if not snapshot:
            return {"created": 0, "recovered": 0, "differences": {}}
        differences = TopologyInferenceService(self.db).compare_snapshot(topology_id, snapshot.id)
        created = 0
        mapping = {
            "added_nodes": ("node_added", "info"), "removed_nodes": ("node_removed", "high"),
            "added_links": ("link_added", "info"), "removed_links": ("link_removed", "high"),
            "layer_changes": ("layer_changed", "warning"), "parent_changes": ("parent_changed", "high"),
        }
        active_keys = set()
        for group, (kind, severity) in mapping.items():
            for value in differences.get(group, []):
                entity_id = value if isinstance(value, str) else value.get("node_id")
                key = f"{kind}:{entity_id}"
                active_keys.add(key)
                existing = self.db.scalar(select(TopologyChange).where(
                    TopologyChange.topology_id == topology_id,
                    TopologyChange.change_type == kind,
                    TopologyChange.source_type == "scheduled_detection",
                    TopologyChange.review_status == "pending",
                    or_(TopologyChange.node_id == entity_id, TopologyChange.link_id == entity_id),
                ))
                if existing:
                    existing.detected_at = datetime.now(timezone.utc)
                    continue
                values = value if isinstance(value, dict) else {"entity_id": value}
                self.db.add(TopologyChange(
                    topology_id=topology_id, snapshot_id=snapshot.id, change_type=kind,
                    entity_type="node" if "node" in kind or kind in {"layer_changed", "parent_changed"} else "link",
                    node_id=entity_id if "node" in kind or kind in {"layer_changed", "parent_changed"} else None,
                    link_id=entity_id if "link" in kind else None,
                    previous_values={"baseline": str(snapshot.id)}, current_values={**values, "severity_hint": severity},
                    source_type="scheduled_detection", confidence_score=100,
                ))
                created += 1
        self.db.commit()
        if created:
            create_audit_log(self.db, actor, "TOPOLOGY_CHANGES_EVALUATED", "Topology", str(topology_id), f"Created {created} deduplicated topology change findings.")
            self.db.commit()
            manager.broadcast_from_thread({"type": "topology_change_detected", "topology_id": str(topology_id), "count": created})
        return {"created": created, "recovered": 0, "differences": differences}

    def evaluate_alerts(self, topology_id, actor="scheduler", preview=False):
        schedule = self.schedule(topology_id)
        health = self.health(topology_id)
        rules = self.db.scalars(select(TopologyAlertRule).where(
            TopologyAlertRule.enabled.is_(True),
            or_(TopologyAlertRule.topology_id.is_(None), TopologyAlertRule.topology_id == topology_id),
        )).all()
        result = {"evaluated": 0, "opened": 0, "updated": 0, "resolved": 0, "suppressed": 0}
        for rule in rules:
            breached, entity_type, entity_id, evidence = self._breach(rule, health, topology_id)
            result["evaluated"] += 1
            if preview:
                result.setdefault("items", []).append({"rule_id": str(rule.id), "would_trigger": breached, "evidence": evidence})
                continue
            entity_clause = (
                TopologyAlertEvent.entity_id == entity_id
                if entity_id is not None
                else TopologyAlertEvent.entity_id.is_(None)
            )
            event = self.db.scalar(select(TopologyAlertEvent).where(
                TopologyAlertEvent.topology_id == topology_id, TopologyAlertEvent.rule_id == rule.id,
                TopologyAlertEvent.entity_type == entity_type,
                entity_clause, TopologyAlertEvent.resolved_at.is_(None),
            ))
            maintenance = schedule.maintenance_mode and rule.suppress_during_maintenance
            if breached and maintenance:
                result["suppressed"] += 1
                continue
            if breached:
                if event:
                    event.occurrence_count += 1; event.recovery_count = 0
                    event.last_seen_at = datetime.now(timezone.utc); event.evidence = evidence
                    event.flapping = event.occurrence_count >= 6
                    if not event.is_open and event.occurrence_count >= rule.consecutive_occurrences:
                        event.is_open = True
                        result["opened"] += 1
                    else:
                        result["updated"] += 1
                else:
                    self.db.add(TopologyAlertEvent(
                        topology_id=topology_id, rule_id=rule.id, entity_type=entity_type,
                        entity_id=entity_id, alert_type=rule.rule_type, severity=rule.severity,
                        evidence=evidence, is_open=rule.consecutive_occurrences <= 1,
                    ))
                    if rule.consecutive_occurrences <= 1:
                        result["opened"] += 1
                    else:
                        result["updated"] += 1
            elif event:
                if not event.is_open:
                    event.resolved_at = datetime.now(timezone.utc)
                    continue
                event.recovery_count += 1
                if event.recovery_count >= rule.recovery_occurrences:
                    event.is_open = False; event.resolved_at = datetime.now(timezone.utc); result["resolved"] += 1
        if not preview:
            create_audit_log(self.db, actor, "TOPOLOGY_ALERTS_EVALUATED", "Topology", str(topology_id), f"Evaluated {result['evaluated']} rules; opened {result['opened']}, resolved {result['resolved']}.")
            self.db.commit()
            if result["opened"]: manager.broadcast_from_thread({"type": "topology_alert_created", "topology_id": str(topology_id), "count": result["opened"]})
            if result["resolved"]: manager.broadcast_from_thread({"type": "topology_alert_recovered", "topology_id": str(topology_id), "count": result["resolved"]})
        return result

    def _breach(self, rule, health, topology_id):
        evidence = {"health": health["overall_status"], "stale": health["stale_topology"], "maintenance": health["maintenance_mode"]}
        if rule.rule_type == "topology_partitioned": return health["connected_component_count"] > (rule.threshold or 1), "topology", None, evidence
        if rule.rule_type == "orphan_count_exceeded": return health["orphan_count"] > (rule.threshold or 0), "topology", None, evidence
        if rule.rule_type == "conflict_count_exceeded": return health["conflict_count"] > (rule.threshold or 0), "topology", None, evidence
        if rule.rule_type == "topology_stale": return health["stale_topology"], "topology", None, evidence
        if rule.rule_type in {"node_missing", "node_restored"} and rule.node_id:
            node = self.db.get(TopologyNode, rule.node_id); missing = not node or node.topology_id != topology_id or node.status == "missing"
            return missing if rule.rule_type == "node_missing" else not missing, "node", rule.node_id, evidence
        if rule.rule_type in {"confirmed_link_missing", "link_restored"} and rule.link_id:
            link = self.db.get(TopologyLink, rule.link_id); missing = not link or link.topology_id != topology_id or link.status == "missing"
            return missing if rule.rule_type == "confirmed_link_missing" else not missing, "link", rule.link_id, evidence
        if rule.rule_type == "low_confidence_link":
            count = self.db.query(TopologyLink).filter(TopologyLink.topology_id == topology_id, TopologyLink.confidence_score < rule.minimum_confidence, TopologyLink.is_suppressed.is_(False)).count()
            return count > (rule.threshold or 0), "topology", None, {**evidence, "low_confidence_links": count}
        return False, "topology", None, evidence

    def retention_preview(self, snapshot_days=90, evidence_days=90, run_days=60):
        now = datetime.now(timezone.utc)
        snapshot_cutoff, evidence_cutoff, run_cutoff = now - timedelta(days=snapshot_days), now - timedelta(days=evidence_days), now - timedelta(days=run_days)
        snapshots = self.db.query(TopologySnapshot).filter(
            TopologySnapshot.created_at < snapshot_cutoff,
            TopologySnapshot.is_operational_baseline.is_(False),
            TopologySnapshot.is_protected.is_(False),
        ).count()
        observations = self.db.query(TopologyNeighborObservation).filter(
            TopologyNeighborObservation.last_seen_at < evidence_cutoff,
            TopologyNeighborObservation.observation_status.in_(("missing", "stale")),
        ).count()
        runs = self.db.query(TopologyOperationalRun).filter(
            TopologyOperationalRun.started_at < run_cutoff,
            TopologyOperationalRun.status.not_in(("running", "pending")),
        ).count()
        return {"eligible_snapshots": snapshots, "eligible_observations": observations, "eligible_evidence": 0, "eligible_runs": runs,
                "protected_records": self.db.query(TopologySnapshot).filter(or_(TopologySnapshot.is_operational_baseline.is_(True), TopologySnapshot.is_protected.is_(True))).count(),
                "snapshot_cutoff": snapshot_cutoff, "evidence_cutoff": evidence_cutoff, "run_cutoff": run_cutoff}

    def cleanup(self, actor, batch_size=500):
        preview = self.retention_preview()
        now = datetime.now(timezone.utc)
        snapshot_ids = self.db.scalars(select(TopologySnapshot.id).where(
            TopologySnapshot.created_at < now - timedelta(days=90),
            TopologySnapshot.is_operational_baseline.is_(False), TopologySnapshot.is_protected.is_(False),
        ).limit(batch_size)).all()
        run_ids = self.db.scalars(select(TopologyOperationalRun.id).where(
            TopologyOperationalRun.started_at < now - timedelta(days=60),
            TopologyOperationalRun.status.not_in(("running", "pending")),
        ).limit(batch_size)).all()
        deleted_snapshots = self.db.query(TopologySnapshot).filter(TopologySnapshot.id.in_(snapshot_ids)).delete(synchronize_session=False) if snapshot_ids else 0
        deleted_runs = self.db.query(TopologyOperationalRun).filter(TopologyOperationalRun.id.in_(run_ids)).delete(synchronize_session=False) if run_ids else 0
        create_audit_log(self.db, actor.username, "TOPOLOGY_RETENTION_CLEANUP", "Topology", None, f"Deleted {deleted_snapshots} eligible snapshots and {deleted_runs} operational runs; protected records preserved.")
        self.db.commit()
        manager.broadcast_from_thread({"type": "topology_cleanup_completed", "deleted_snapshots": deleted_snapshots, "deleted_runs": deleted_runs})
        return {**preview, "deleted_snapshots": deleted_snapshots, "deleted_runs": deleted_runs}

    def export_csv(self, topology_id, kind):
        output = StringIO(newline="")
        writer = csv.writer(output)
        if kind == "nodes":
            writer.writerow(["id", "label", "type", "role", "layer", "status", "vendor", "model", "confidence"])
            for row in self.db.query(TopologyNode).filter_by(topology_id=topology_id).limit(settings.topology_maximum_graph_nodes):
                writer.writerow([_safe_csv(x) for x in (row.id, row.label, row.node_type, row.role, row.layer, row.status, row.vendor, row.model, row.confidence_score)])
        elif kind == "links":
            writer.writerow(["id", "source_node_id", "target_node_id", "type", "status", "speed_bps", "vlan", "confidence", "confirmed"])
            for row in self.db.query(TopologyLink).filter_by(topology_id=topology_id).limit(settings.topology_maximum_graph_links):
                writer.writerow([_safe_csv(x) for x in (row.id, row.source_node_id, row.target_node_id, row.link_type, row.status, row.speed_bps, row.vlan_id, row.confidence_score, row.is_confirmed)])
        else:
            raise HTTPException(400, "Unsupported topology export type.")
        return output.getvalue()
