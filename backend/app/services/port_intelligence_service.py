"""V3B read-only switch/interface collection and identity correlation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.config import settings
from app.models.device import Device
from app.models.port_intelligence import PortDeviceAssociation
from app.models.snmp import SNMPInterface, SNMPTarget
from app.models.topology import TopologyLink, TopologyNode
from app.models.topology_neighbor import TopologyNeighborCandidate, TopologyNeighborObservation
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery
from app.services.snmp_client_service import SecureSNMPClient
from app.services.snmp_polling_service import SNMPPollingService
from app.services.topology_v3a_service import V3ATopologyService, confidence_level, normalize_mac

BRIDGE_FDB_ADDRESS_OID = "1.3.6.1.2.1.17.4.3.1.1"
BRIDGE_FDB_PORT_OID = "1.3.6.1.2.1.17.4.3.1.2"
BRIDGE_BASE_PORT_IFINDEX_OID = "1.3.6.1.2.1.17.1.4.1.2"


@dataclass(frozen=True)
class PortMACObservation:
    interface_index: int
    mac_address: str


def mac_from_oid(oid: str, root: str) -> str | None:
    suffix = oid.removeprefix(root + ".")
    try:
        octets = [int(part) for part in suffix.split(".")]
    except ValueError:
        return None
    if len(octets) != 6 or any(value < 0 or value > 255 for value in octets):
        return None
    return ":".join(f"{value:02x}" for value in octets)


def status_name(value: str | None) -> str:
    return {"1": "up", "2": "down", "3": "testing"}.get(str(value or ""), str(value or "unknown").lower())


class PortMACTableProvider:
    """Bounded BRIDGE-MIB reads only; no SNMP SET operation is exposed."""

    def __init__(self, db, client_factory=SecureSNMPClient):
        self.db = db
        self.client_factory = client_factory

    def collect(self, target: SNMPTarget) -> list[PortMACObservation]:
        discovery = read_discovery(self.db)
        networks = discovery.get("authorized_cidr_ranges", [])
        ignored = discovery.get("ignore_ranges", [])
        if isinstance(networks, str):
            networks = [item.strip() for item in networks.split(",") if item.strip()]
        if isinstance(ignored, str):
            ignored = [item.strip() for item in ignored.split(",") if item.strip()]
        client = self.client_factory(target, target.credential, authorized_networks=networks, ignored_networks=ignored)
        bounds = {
            "max_rows": min(settings.topology_neighbor_maximum_per_target, settings.snmp_maximum_walk_rows),
            "max_duration": settings.topology_neighbor_maximum_duration_seconds,
        }
        try:
            addresses = client.bulk_walk(BRIDGE_FDB_ADDRESS_OID, **bounds)
            ports = client.bulk_walk(BRIDGE_FDB_PORT_OID, **bounds)
            port_indexes = client.bulk_walk(BRIDGE_BASE_PORT_IFINDEX_OID, **bounds)
            macs = {}
            for item in addresses.items:
                mac = normalize_mac(item.value_text if item.value_text is not None else item.value_numeric) or mac_from_oid(item.oid, BRIDGE_FDB_ADDRESS_OID)
                if mac:
                    macs[item.oid.removeprefix(BRIDGE_FDB_ADDRESS_OID + ".")] = mac
            fdb_ports = {
                item.oid.removeprefix(BRIDGE_FDB_PORT_OID + "."): int(item.value_numeric)
                for item in ports.items if item.value_numeric is not None
            }
            if_indexes = {
                int(item.oid.removeprefix(BRIDGE_BASE_PORT_IFINDEX_OID + ".")): int(item.value_numeric)
                for item in port_indexes.items if item.value_numeric is not None
            }
            return [
                PortMACObservation(if_indexes[bridge_port], mac)
                for suffix, mac in macs.items()
                if (bridge_port := fdb_ports.get(suffix)) in if_indexes
            ]
        finally:
            client.close()


class PortIntelligenceService:
    def __init__(self, db, mac_provider=None, polling_factory=SNMPPollingService, organization_id=None, property_id=None):
        self.db = db
        self.organization_id = organization_id
        self.property_id = property_id
        self.mac_provider = mac_provider or PortMACTableProvider(db)
        self.polling_factory = polling_factory

    def _scoped_device(self, device_id: UUID) -> Device | None:
        query = select(Device).where(Device.id == device_id)
        if self.property_id:
            query = query.where(Device.property_id == self.property_id)
        elif self.organization_id:
            from app.models.hierarchy import Property
            query = query.join(Property, Device.property_id == Property.id).where(Property.organization_id == self.organization_id)
        return self.db.scalar(query)

    def _target(self, switch_device_id: UUID) -> SNMPTarget | None:
        return self.db.scalar(select(SNMPTarget).where(
            SNMPTarget.device_id == switch_device_id, SNMPTarget.enabled.is_(True),
        ).order_by(SNMPTarget.updated_at.desc()))

    def _device_index(self) -> dict[str, list[Device]]:
        result = defaultdict(list)
        for row in self.db.scalars(select(Device).where(Device.mac_address.is_not(None))).all():
            if mac := normalize_mac(row.mac_address):
                result[mac].append(row)
        return result

    def _uplinks(self, switch_device_id: UUID, interfaces: list[SNMPInterface]) -> dict[UUID, Device]:
        observations = self.db.scalars(select(TopologyNeighborObservation).where(
            TopologyNeighborObservation.source_device_id == switch_device_id,
            TopologyNeighborObservation.observation_status == "current",
        )).all()
        candidates = self.db.scalars(select(TopologyNeighborCandidate).where(
            TopologyNeighborCandidate.source_observation_id.in_([row.id for row in observations]),
            TopologyNeighborCandidate.matched_device_id.is_not(None),
        )).all() if observations else []
        matched = {row.source_observation_id: self.db.get(Device, row.matched_device_id) for row in candidates}
        by_identifier = {}
        for interface in interfaces:
            for value in (interface.name, interface.description, str(interface.interface_index)):
                if value:
                    by_identifier[str(value).strip().lower()] = interface
        result = {}
        for observation in observations:
            peer = matched.get(observation.id)
            interface = by_identifier.get(observation.local_port_identifier.strip().lower())
            if peer and interface and peer.id != switch_device_id:
                result[interface.id] = peer
        return result

    def _find_association(self, interface_id, mac, device_id):
        query = select(PortDeviceAssociation).where(
            PortDeviceAssociation.interface_id == interface_id,
            PortDeviceAssociation.observed_mac == mac,
        )
        query = query.where(PortDeviceAssociation.connected_device_id == device_id) if device_id else query.where(PortDeviceAssociation.connected_device_id.is_(None))
        return self.db.scalar(query)

    def _topology_link(self, switch: Device, endpoint: Device, interface: SNMPInterface, actor, confidence: int):
        topology = V3ATopologyService(self.db).ensure_default_topology(actor)
        link, _ = V3ATopologyService(self.db).upsert_relationship(
            topology, switch, endpoint, "UPLINK_TO" if "switch" in endpoint.device_type.lower() else "CONNECTED_TO",
            "SNMP_MAC_TABLE", confidence, actor,
            evidence_value=f"{interface.name or interface.interface_index}: MAC table matched existing device identity",
        )
        if link:
            source_node = self.db.get(TopologyNode, link.source_node_id)
            if source_node and source_node.device_id == switch.id:
                link.source_interface_id = interface.id
            else:
                link.target_interface_id = interface.id
            link.speed_bps = interface.speed_bps
            link.duplex = interface.duplex
            link.metadata_json = {**(link.metadata_json or {}), "port_name": interface.name, "port_description": interface.description}
        return link

    def _upsert(self, switch, interface, mac, endpoint, association_type, confidence, explanation, evidence, actor, now):
        row = self._find_association(interface.id, mac, endpoint.id if endpoint else None)
        if not row:
            row = PortDeviceAssociation(
                switch_device_id=switch.id, interface_id=interface.id, connected_device_id=endpoint.id if endpoint else None,
                observed_mac=mac, association_type=association_type, confidence_score=confidence,
                confidence_level=confidence_level(confidence), confidence_explanation=explanation,
                evidence=evidence, first_observed_at=now, last_observed_at=now, is_current=True,
            )
            self.db.add(row)
            self.db.flush()
        else:
            row.last_observed_at = now
            row.is_current = True
            row.stale_at = None
            row.confidence_score = confidence
            row.confidence_level = confidence_level(confidence)
            row.confidence_explanation = explanation
            row.evidence = evidence
            row.association_type = association_type
        if endpoint:
            for previous in self.db.scalars(select(PortDeviceAssociation).where(
                PortDeviceAssociation.connected_device_id == endpoint.id,
                PortDeviceAssociation.is_current.is_(True),
                PortDeviceAssociation.interface_id != interface.id,
            )).all():
                if previous.connected_device_id == endpoint.id and previous.is_current and previous.interface_id != interface.id:
                    previous.is_current = False
                    previous.stale_at = now
            link = self._topology_link(switch, endpoint, interface, actor, confidence)
            row.topology_link_id = link.id if link else None
        return row

    def correlate(self, switch: Device, observations: list[PortMACObservation], actor, *, complete=True, observed_at=None) -> dict:
        now = observed_at or datetime.now(timezone.utc)
        target = self._target(switch.id)
        if not target:
            raise HTTPException(409, "Port-level information unavailable because the switch has no linked SNMP target.")
        interfaces = self.db.scalars(select(SNMPInterface).where(SNMPInterface.target_id == target.id)).all()
        by_index = {row.interface_index: row for row in interfaces}
        uplinks = self._uplinks(switch.id, interfaces)
        devices_by_mac = self._device_index()
        seen = set()
        resolved = unresolved = uplink_count = 0

        for interface_id, peer in uplinks.items():
            interface = next(row for row in interfaces if row.id == interface_id)
            row = self._upsert(
                switch, interface, normalize_mac(peer.mac_address), peer, "uplink", 95,
                "High confidence from V3A LLDP/CDP neighbor evidence matched to an existing switch.",
                [{"source": "LLDP_CDP", "type": "switch_neighbor", "value": peer.hostname},
                 {"source": "interface", "type": "active", "value": status_name(interface.operational_status)}], actor, now,
            )
            seen.add(row.id); uplink_count += 1

        for observation in observations:
            interface = by_index.get(observation.interface_index)
            if not interface or interface.id in uplinks:
                continue
            matches = [row for row in devices_by_mac.get(observation.mac_address, []) if row.id != switch.id]
            endpoint = matches[0] if len(matches) == 1 else None
            active = status_name(interface.operational_status) == "up"
            confidence = 90 if endpoint and active else 80 if endpoint else 35 if not matches else 25
            explanation = (
                "High confidence: MAC table, known inventory MAC, and active interface agree." if endpoint and active else
                "High confidence: MAC table matched a known inventory MAC; interface state is not active." if endpoint else
                "Low confidence: MAC table entry does not uniquely match an existing device; association requires review."
            )
            evidence = [
                {"source": "SNMP_MAC_TABLE", "type": "mac_observed", "value": observation.mac_address},
                {"source": "V2_IDENTITY", "type": "mac_match", "value": endpoint.hostname if endpoint else "unresolved"},
                {"source": "SNMP_INTERFACE", "type": "operational_status", "value": status_name(interface.operational_status)},
            ]
            row = self._upsert(switch, interface, observation.mac_address, endpoint, "endpoint" if endpoint else "unknown", confidence, explanation, evidence, actor, now)
            seen.add(row.id)
            resolved += int(endpoint is not None)
            unresolved += int(endpoint is None)

        if complete:
            for row in self.db.scalars(select(PortDeviceAssociation).where(
                PortDeviceAssociation.switch_device_id == switch.id,
                PortDeviceAssociation.is_current.is_(True),
            )).all():
                if row.switch_device_id == switch.id and row.is_current and row.id not in seen:
                    row.is_current = False
                    row.stale_at = now
        create_audit_log(self.db, actor.username, "V3B_PORT_INTELLIGENCE_REFRESHED", "Device", str(switch.id), f"Read-only port correlation stored {resolved} endpoint and {uplink_count} uplink associations; {unresolved} unresolved.")
        self.db.commit()
        return {"resolved": resolved, "unresolved": unresolved, "uplinks": uplink_count, "observed": len(observations), "interfaces": len(interfaces)}

    def refresh(self, switch_device_id: UUID, actor) -> dict:
        switch = self._scoped_device(switch_device_id)
        if not switch:
            raise HTTPException(404, "Switch device was not found.")
        target = self._target(switch.id)
        if not settings.snmp_enabled or not target:
            return {"status": "unavailable", "message": "Port-level information unavailable because SNMP is disabled or no linked target exists.", "interfaces": 0, "observed": 0, "resolved": 0, "unresolved": 0, "uplinks": 0}
        poller = self.polling_factory(self.db)
        run = poller.create_poll_run(target.id, actor, "interfaces_preview")
        run = poller.execute_poll(run.id, actor)
        if run.status == "failed":
            return {"status": "unavailable", "message": run.error_summary or "Interface data unavailable.", "interfaces": 0, "observed": 0, "resolved": 0, "unresolved": 0, "uplinks": 0}
        observations = self.mac_provider.collect(target)
        result = self.correlate(switch, observations, actor, complete=True)
        return {"status": "complete" if run.status == "completed" else "partial", "message": "Read-only interface and MAC-table refresh completed.", **result}

    def switch_interfaces(self, switch_device_id: UUID, search=None, status=None, endpoint=None) -> dict:
        switch = self._scoped_device(switch_device_id)
        if not switch:
            raise HTTPException(404, "Switch device was not found.")
        target = self._target(switch.id)
        if not target:
            return {"switch": self._device(switch), "items": [], "total": 0, "data_state": "unavailable", "message": "Port-level information unavailable: no linked SNMP target."}
        interfaces = self.db.scalars(select(SNMPInterface).where(SNMPInterface.target_id == target.id).order_by(SNMPInterface.interface_index)).all()
        items = [self._interface(row, include_history=False) for row in interfaces]
        if search:
            needle = search.lower()
            items = [item for item in items if needle in str(item).lower()]
        if status == "active":
            items = [item for item in items if item["operational_status"] == "up"]
        if endpoint == "unknown":
            items = [item for item in items if item["endpoint_state"] in {"unknown", "multiple"}]
        return {"switch": self._device(switch), "items": items, "total": len(items), "data_state": "current" if items else "no_interfaces", "message": None if items else "Interface data unavailable or not yet collected."}

    def interface(self, interface_id: UUID) -> dict:
        row = self.db.get(SNMPInterface, interface_id)
        target = self.db.get(SNMPTarget, row.target_id) if row else None
        if not row or not target or not target.device_id or not self._scoped_device(target.device_id):
            raise HTTPException(404, "Interface was not found.")
        return self._interface(row, include_history=True)

    def device_connection(self, device_id: UUID) -> dict:
        device = self._scoped_device(device_id)
        if not device:
            raise HTTPException(404, "Device was not found.")
        current = self.db.scalars(select(PortDeviceAssociation).where(
            PortDeviceAssociation.connected_device_id == device.id,
            PortDeviceAssociation.is_current.is_(True),
        ).order_by(PortDeviceAssociation.confidence_score.desc(), PortDeviceAssociation.last_observed_at.desc())).all()
        history = self.db.scalars(select(PortDeviceAssociation).where(
            PortDeviceAssociation.connected_device_id == device.id,
            PortDeviceAssociation.is_current.is_(False),
        ).order_by(PortDeviceAssociation.last_observed_at.desc()).limit(25)).all()
        return {
            "device_id": str(device.id), "current": self._association(current[0]) if current else None,
            "multiple_current": len(current) > 1, "history": [self._association(row) for row in history],
            "data_state": "current" if current else "unknown",
            "message": None if current else "Port-level information unavailable or the exact port association requires review.",
        }

    def stats(self) -> dict:
        device_query = select(Device.id)
        if self.property_id:
            device_query = device_query.where(Device.property_id == self.property_id)
        elif self.organization_id:
            from app.models.hierarchy import Property
            device_query = device_query.join(Property, Device.property_id == Property.id).where(Property.organization_id == self.organization_id)
        target_ids = select(SNMPTarget.id).where(SNMPTarget.device_id.in_(device_query))
        interfaces = self.db.scalars(select(SNMPInterface).where(SNMPInterface.target_id.in_(target_ids))).all()
        interface_ids = [row.id for row in interfaces]
        associations = self.db.scalars(select(PortDeviceAssociation).where(PortDeviceAssociation.interface_id.in_(interface_ids))).all() if interface_ids else []
        current = [row for row in associations if row.is_current]
        return {
            "network_devices_with_interfaces": len({row.target_id for row in interfaces}),
            "interfaces_discovered": len(interfaces),
            "port_device_associations": sum(row.connected_device_id is not None for row in current),
            "uplinks_identified": sum(row.association_type == "uplink" for row in current),
            "unknown_port_associations": sum(row.connected_device_id is None for row in current),
            "stale_associations": sum(not row.is_current for row in associations),
            "duplicates": 0,
        }

    def _interface(self, row: SNMPInterface, *, include_history: bool) -> dict:
        associations = self.db.scalars(select(PortDeviceAssociation).where(
            PortDeviceAssociation.interface_id == row.id,
            PortDeviceAssociation.is_current.is_(True),
        ).order_by(PortDeviceAssociation.confidence_score.desc())).all()
        history = self.db.scalars(select(PortDeviceAssociation).where(
            PortDeviceAssociation.interface_id == row.id,
            PortDeviceAssociation.is_current.is_(False),
        ).order_by(PortDeviceAssociation.last_observed_at.desc()).limit(25)).all() if include_history else []
        known = [item for item in associations if item.connected_device_id]
        endpoint_state = "multiple" if len(associations) > 1 else "known" if known else "unknown"
        return {
            "id": str(row.id), "interface_index": row.interface_index, "name": row.name,
            "description": row.description, "alias": row.alias, "admin_status": status_name(row.admin_status),
            "operational_status": status_name(row.operational_status), "speed_bps": row.speed_bps,
            "duplex": row.duplex, "mac_address": normalize_mac(row.mac_address), "last_observed_at": row.last_seen_at,
            "is_missing": row.is_missing, "endpoint_state": endpoint_state,
            "associations": [self._association(item) for item in associations],
            "history": [self._association(item) for item in history],
        }

    def _association(self, row: PortDeviceAssociation) -> dict:
        interface = self.db.get(SNMPInterface, row.interface_id)
        switch = self.db.get(Device, row.switch_device_id)
        endpoint = self.db.get(Device, row.connected_device_id) if row.connected_device_id else None
        return {
            "id": str(row.id), "switch": self._device(switch),
            "interface": {"id": str(interface.id), "name": interface.name, "description": interface.description,
                          "admin_status": status_name(interface.admin_status), "operational_status": status_name(interface.operational_status),
                          "speed_bps": interface.speed_bps, "duplex": interface.duplex} if interface else None,
            "connected_device": self._device(endpoint) if endpoint else None,
            "observed_mac": row.observed_mac, "association_type": row.association_type,
            "evidence_source": row.evidence_source, "evidence": row.evidence,
            "confidence": row.confidence_score, "confidence_level": row.confidence_level,
            "confidence_explanation": row.confidence_explanation,
            "first_observed_at": row.first_observed_at, "last_observed_at": row.last_observed_at,
            "state": "current" if row.is_current else "stale", "stale_at": row.stale_at,
        }

    @staticmethod
    def _device(device: Device | None):
        return None if not device else {"id": str(device.id), "hostname": device.hostname, "device_type": device.device_type, "ip_address": device.ip_address, "mac_address": normalize_mac(device.mac_address)}
