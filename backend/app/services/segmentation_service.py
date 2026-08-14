"""V3C read-only VLAN collection, correlation, history, and query service."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.models.device import Device
from app.models.port_intelligence import PortDeviceAssociation
from app.models.segmentation import VLANMembershipObservation
from app.models.snmp import SNMPInterface, SNMPTarget
from app.models.topology import NetworkSegment, Topology, TopologyNode, TopologyNodeSegment
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery
from app.services.snmp_client_service import SecureSNMPClient
from app.services.topology_v3a_service import V3ATopologyService, confidence_level

VLAN_NAME_OID = "1.3.6.1.2.1.17.7.1.4.3.1.1"
VLAN_EGRESS_OID = "1.3.6.1.2.1.17.7.1.4.3.1.2"
VLAN_UNTAGGED_OID = "1.3.6.1.2.1.17.7.1.4.3.1.4"
VLAN_STATUS_OID = "1.3.6.1.2.1.17.7.1.4.3.1.5"
PORT_PVID_OID = "1.3.6.1.2.1.17.7.1.4.5.1.1"
BRIDGE_BASE_PORT_IFINDEX_OID = "1.3.6.1.2.1.17.1.4.1.2"


@dataclass(frozen=True)
class VLANRecord:
    vlan_id: int
    name: str | None = None
    status: str = "unknown"
    description: str | None = None
    cidr: str | None = None
    gateway: str | None = None


@dataclass(frozen=True)
class PortVLANRecord:
    interface_index: int
    vlan_id: int
    membership_type: str
    port_mode: str


def _suffix_int(oid: str, root: str) -> int | None:
    try:
        return int(oid.removeprefix(root + ".").split(".")[-1])
    except (ValueError, IndexError):
        return None


def _bitmap_ports(value) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, bytes):
        raw = value
    else:
        text = str(value).replace("0x", "").replace(" ", "").replace(":", "")
        try:
            raw = bytes.fromhex(text)
        except ValueError:
            return set()
    return {byte_index * 8 + bit + 1 for byte_index, byte in enumerate(raw) for bit in range(8) if byte & (0x80 >> bit)}


class VLANTableProvider:
    """Bounded Q-BRIDGE-MIB GET-BULK reads; there is deliberately no SET path."""
    def __init__(self, db, client_factory=SecureSNMPClient):
        self.db, self.client_factory = db, client_factory

    def collect(self, target: SNMPTarget) -> tuple[list[VLANRecord], list[PortVLANRecord]]:
        discovery = read_discovery(self.db)
        allowed, ignored = discovery.get("authorized_cidr_ranges", []), discovery.get("ignore_ranges", [])
        if isinstance(allowed, str): allowed = [x.strip() for x in allowed.split(",") if x.strip()]
        if isinstance(ignored, str): ignored = [x.strip() for x in ignored.split(",") if x.strip()]
        client = self.client_factory(target, target.credential, authorized_networks=allowed, ignored_networks=ignored)
        bounds = {"max_rows": settings.snmp_maximum_walk_rows, "max_duration": settings.topology_neighbor_maximum_duration_seconds}
        try:
            walks = {root: client.bulk_walk(root, **bounds).items for root in (VLAN_NAME_OID, VLAN_STATUS_OID, VLAN_EGRESS_OID, VLAN_UNTAGGED_OID, PORT_PVID_OID, BRIDGE_BASE_PORT_IFINDEX_OID)}
        finally:
            client.close()
        names = {_suffix_int(x.oid, VLAN_NAME_OID): x.value_text for x in walks[VLAN_NAME_OID]}
        statuses = {_suffix_int(x.oid, VLAN_STATUS_OID): {1: "unknown", 2: "active", 3: "active"}.get(int(x.value_numeric or 0), "unknown") for x in walks[VLAN_STATUS_OID]}
        vlan_ids = {v for v in names | statuses if v and 1 <= v <= 4094}
        vlans = [VLANRecord(v, names.get(v), statuses.get(v, "unknown")) for v in sorted(vlan_ids)]
        bridge_to_if = {_suffix_int(x.oid, BRIDGE_BASE_PORT_IFINDEX_OID): int(x.value_numeric) for x in walks[BRIDGE_BASE_PORT_IFINDEX_OID] if x.value_numeric is not None}
        egress, untagged = defaultdict(set), defaultdict(set)
        for root, target_map in ((VLAN_EGRESS_OID, egress), (VLAN_UNTAGGED_OID, untagged)):
            for item in walks[root]:
                vlan = _suffix_int(item.oid, root)
                for bridge_port in _bitmap_ports(item.value_text):
                    if vlan and bridge_port in bridge_to_if: target_map[bridge_to_if[bridge_port]].add(vlan)
        pvid = {bridge_to_if.get(_suffix_int(x.oid, PORT_PVID_OID)): int(x.value_numeric) for x in walks[PORT_PVID_OID] if x.value_numeric is not None}
        ports = []
        for if_index in set(egress) | set(untagged) | {x for x in pvid if x}:
            carried = egress[if_index] | untagged[if_index] | ({pvid[if_index]} if if_index in pvid else set())
            mode = "trunk" if len(carried) > 1 else "access" if carried else "unknown"
            for vlan in sorted(carried):
                kind = "native" if pvid.get(if_index) == vlan and mode == "trunk" else "access" if mode == "access" else "allowed"
                ports.append(PortVLANRecord(if_index, vlan, kind, mode))
        return vlans, ports


class SegmentationService:
    def __init__(self, db, provider=None, organization_id=None, property_id=None):
        self.db, self.provider = db, provider or VLANTableProvider(db)
        self.organization_id, self.property_id = organization_id, property_id

    def _device_query(self):
        query = select(Device.id)
        if self.property_id:
            return query.where(Device.property_id == self.property_id)
        if self.organization_id:
            from app.models.hierarchy import Property
            return query.join(Property, Device.property_id == Property.id).where(Property.organization_id == self.organization_id)
        return query

    def _scoped_device(self, device_id):
        return self.db.scalar(select(Device).where(Device.id == device_id, Device.id.in_(self._device_query())))

    def _target(self, device_id):
        return self.db.scalar(select(SNMPTarget).where(SNMPTarget.device_id == device_id, SNMPTarget.enabled.is_(True)).order_by(SNMPTarget.updated_at.desc()))

    def _topology(self, actor=None):
        row = self.db.scalar(select(Topology).order_by(Topology.is_default.desc(), Topology.created_at))
        return row or (V3ATopologyService(self.db).ensure_default_topology(actor) if actor else None)

    def _segment(self, topology, record, now):
        row = self.db.scalar(select(NetworkSegment).where(NetworkSegment.topology_id == topology.id, NetworkSegment.vlan_id == record.vlan_id))
        if not row:
            row = NetworkSegment(topology_id=topology.id, name=record.name or f"VLAN {record.vlan_id}", vlan_id=record.vlan_id, vlan_name=record.name, cidr=record.cidr, description=record.description, vlan_status=record.status, gateway=record.gateway, source_type="SNMP_Q_BRIDGE", confidence_score=85, first_seen_at=now, last_seen_at=now)
            self.db.add(row); self.db.flush()
        else:
            row.name, row.vlan_name, row.vlan_status, row.last_seen_at, row.stale_at = record.name or row.name, record.name or row.vlan_name, record.status, now, None
            if record.cidr is not None: row.cidr = record.cidr
            if record.gateway is not None: row.gateway = record.gateway
            if record.description is not None: row.description = record.description
        return row

    def _membership(self, segment, switch, interface, connected, port_assoc, record, now):
        q = select(VLANMembershipObservation).where(VLANMembershipObservation.network_segment_id == segment.id, VLANMembershipObservation.interface_id == interface.id, VLANMembershipObservation.membership_type == record.membership_type)
        q = q.where(VLANMembershipObservation.connected_device_id == connected.id) if connected else q.where(VLANMembershipObservation.connected_device_id.is_(None))
        row = self.db.scalar(q)
        confidence = 95 if connected and record.port_mode == "access" else 85 if record.port_mode == "trunk" else 70
        explanation = "High confidence: Q-BRIDGE port VLAN evidence and the existing V3B MAC/device association agree." if connected else "VLAN membership is confirmed for the interface; endpoint identity is not required or remains unknown."
        evidence = [{"source":"SNMP_Q_BRIDGE","type":"port_vlan","value":f"VLAN {segment.vlan_id}"},{"source":"V3B_PORT","type":"port_mode","value":record.port_mode}]
        if not row:
            row = VLANMembershipObservation(network_segment_id=segment.id, switch_device_id=switch.id, interface_id=interface.id, connected_device_id=connected.id if connected else None, port_association_id=port_assoc.id if port_assoc else None, membership_type=record.membership_type, port_mode=record.port_mode, evidence=evidence, confidence_score=confidence, confidence_explanation=explanation, first_observed_at=now, last_observed_at=now)
            self.db.add(row); self.db.flush()
        else:
            row.last_observed_at, row.is_current, row.stale_at = now, True, None
            row.port_mode, row.evidence, row.confidence_score, row.confidence_explanation = record.port_mode, evidence, confidence, explanation
        if connected and record.port_mode == "access":
            for old in self.db.scalars(select(VLANMembershipObservation).where(VLANMembershipObservation.connected_device_id == connected.id, VLANMembershipObservation.is_current.is_(True), VLANMembershipObservation.id != row.id)).all():
                if old.network_segment_id != segment.id: old.is_current, old.stale_at = False, now
        # Enrich the existing V3A graph; never create a parallel topology graph.
        topology = self.db.get(Topology, segment.topology_id)
        node_devices = [(switch.id, record.membership_type)] + ([(connected.id, "device")] if connected else [])
        for device_id, membership_type in node_devices:
            node = self.db.scalar(select(TopologyNode).where(TopologyNode.topology_id == topology.id, TopologyNode.device_id == device_id))
            if not node:
                continue
            node_segment = self.db.scalar(select(TopologyNodeSegment).where(
                TopologyNodeSegment.topology_node_id == node.id,
                TopologyNodeSegment.network_segment_id == segment.id,
                TopologyNodeSegment.interface_id == interface.id,
            ))
            if not node_segment:
                self.db.add(TopologyNodeSegment(topology_node_id=node.id, network_segment_id=segment.id, interface_id=interface.id, membership_type=membership_type, source_type="SNMP_Q_BRIDGE", confidence_score=confidence, first_seen_at=now, last_seen_at=now))
            else:
                node_segment.membership_type, node_segment.confidence_score, node_segment.last_seen_at = membership_type, confidence, now
        if connected and port_assoc and port_assoc.topology_link_id and record.port_mode == "access":
            from app.models.topology import TopologyLink
            link = self.db.get(TopologyLink, port_assoc.topology_link_id)
            if link:
                link.vlan_id = segment.vlan_id
                link.metadata_json = {**(link.metadata_json or {}), "vlan_name": segment.vlan_name or segment.name, "segment_id": str(segment.id)}
        return row

    def correlate(self, switch, vlan_records, port_records, actor, observed_at=None, complete=True):
        now, topology = observed_at or datetime.now(timezone.utc), self._topology(actor)
        target = self._target(switch.id)
        if not target: raise HTTPException(409, "VLAN information unavailable because the switch has no linked SNMP target.")
        interfaces = {x.interface_index:x for x in self.db.scalars(select(SNMPInterface).where(SNMPInterface.target_id == target.id)).all()}
        segments = {record.vlan_id:self._segment(topology, record, now) for record in vlan_records}
        associations = defaultdict(list)
        for row in self.db.scalars(select(PortDeviceAssociation).where(PortDeviceAssociation.switch_device_id == switch.id, PortDeviceAssociation.is_current.is_(True))).all(): associations[row.interface_id].append(row)
        seen, endpoint_count, trunk_count = set(), 0, 0
        for record in port_records:
            interface, segment = interfaces.get(record.interface_index), segments.get(record.vlan_id)
            if not interface or not segment: continue
            candidates = associations[interface.id]
            endpoints = [x for x in candidates if x.connected_device_id and (record.port_mode == "access" or x.association_type == "uplink")]
            if not endpoints:
                seen.add(self._membership(segment, switch, interface, None, None, record, now).id)
            for association in endpoints:
                endpoint = self.db.get(Device, association.connected_device_id)
                if endpoint:
                    seen.add(self._membership(segment, switch, interface, endpoint, association, record, now).id); endpoint_count += 1
            trunk_count += int(record.port_mode == "trunk")
        if complete:
            for old in self.db.scalars(select(VLANMembershipObservation).where(VLANMembershipObservation.switch_device_id == switch.id, VLANMembershipObservation.is_current.is_(True))).all():
                if old.id not in seen: old.is_current, old.stale_at = False, now
        create_audit_log(self.db, actor.username, "V3C_VLAN_INTELLIGENCE_REFRESHED", "Device", str(switch.id), f"Read-only VLAN refresh stored {len(segments)} VLANs and {len(seen)} memberships.")
        self.db.commit()
        return {"vlans":len(segments),"memberships":len(seen),"devices":endpoint_count,"trunks":trunk_count}

    def refresh(self, switch_device_id: UUID, actor):
        switch, target = self._scoped_device(switch_device_id), self._target(switch_device_id)
        if not switch: raise HTTPException(404, "Switch device was not found.")
        if not settings.snmp_enabled or not target: return {"status":"unavailable","message":"VLAN information unavailable because SNMP is disabled or no linked target exists.","vlans":0,"memberships":0,"devices":0,"trunks":0}
        try: vlans, ports = self.provider.collect(target)
        except Exception as exc: return {"status":"unavailable","message":f"Read-only VLAN collection failed: {exc}","vlans":0,"memberships":0,"devices":0,"trunks":0}
        result = self.correlate(switch, vlans, ports, actor)
        return {"status":"complete","message":"Read-only VLAN intelligence refresh completed.",**result}

    @staticmethod
    def _device(row):
        return {"id":str(row.id),"hostname":row.hostname,"device_type":row.device_type,"ip_address":row.ip_address,"mac_address":row.mac_address}

    def _item(self, segment):
        memberships = self.db.scalars(select(VLANMembershipObservation).where(VLANMembershipObservation.network_segment_id == segment.id, VLANMembershipObservation.is_current.is_(True))).all()
        return {"id":str(segment.id),"vlan_id":segment.vlan_id,"name":segment.vlan_name or segment.name,"description":segment.description,"status":"stale" if segment.stale_at else segment.vlan_status,"subnet":segment.cidr,"gateway":segment.gateway,"source":segment.source_type,"confidence":segment.confidence_score,"confidence_level":confidence_level(segment.confidence_score),"first_observed_at":segment.first_seen_at,"last_observed_at":segment.last_seen_at,"device_count":len({x.connected_device_id for x in memberships if x.connected_device_id}),"port_count":len({x.interface_id for x in memberships}),"trunk_ports":len({x.interface_id for x in memberships if x.port_mode=="trunk"})}

    def list_vlans(self, search=None, vlan_id=None, subnet=None, switch=None, port=None):
        topology = self._topology()
        if not topology: return {"items":[],"total":0,"data_state":"unavailable","message":"No topology exists yet."}
        scoped_segments = select(VLANMembershipObservation.network_segment_id).where(VLANMembershipObservation.switch_device_id.in_(self._device_query()))
        rows = self.db.scalars(select(NetworkSegment).where(NetworkSegment.topology_id == topology.id, NetworkSegment.vlan_id.is_not(None), NetworkSegment.id.in_(scoped_segments)).order_by(NetworkSegment.vlan_id)).all()
        items = [self._item(x) for x in rows]
        needle = (search or "").lower()
        if needle: items = [x for x in items if needle in str(x).lower()]
        if vlan_id is not None: items = [x for x in items if x["vlan_id"] == vlan_id]
        if subnet: items = [x for x in items if x["subnet"] == subnet]
        if switch or port:
            query = select(VLANMembershipObservation).join(Device, Device.id==VLANMembershipObservation.switch_device_id).join(SNMPInterface, SNMPInterface.id==VLANMembershipObservation.interface_id)
            if switch: query = query.where(func.lower(Device.hostname).contains(switch.lower()))
            if port: query = query.where(func.lower(SNMPInterface.name).contains(port.lower()))
            allowed = {str(x.network_segment_id) for x in self.db.scalars(query).all()}
            items = [x for x in items if x["id"] in allowed]
        return {"items":items,"total":len(items),"data_state":"current" if items else "no_segments","message":None if items else "No VLAN observations are available."}

    def vlan_details(self, segment_id):
        segment = self.db.scalar(select(NetworkSegment).where(NetworkSegment.id == segment_id, NetworkSegment.id.in_(select(VLANMembershipObservation.network_segment_id).where(VLANMembershipObservation.switch_device_id.in_(self._device_query())))))
        if not segment or segment.vlan_id is None: raise HTTPException(404,"VLAN was not found.")
        rows = self.db.scalars(select(VLANMembershipObservation).where(VLANMembershipObservation.network_segment_id==segment.id,VLANMembershipObservation.switch_device_id.in_(self._device_query())).order_by(VLANMembershipObservation.is_current.desc(), VLANMembershipObservation.last_observed_at.desc())).all()
        memberships=[]
        for row in rows:
            interface, switch = self.db.get(SNMPInterface,row.interface_id), self.db.get(Device,row.switch_device_id)
            endpoint = self.db.get(Device,row.connected_device_id) if row.connected_device_id else None
            memberships.append({"id":str(row.id),"switch":self._device(switch),"interface":{"id":str(interface.id),"name":interface.name,"description":interface.description,"operational_status":interface.operational_status},"device":self._device(endpoint) if endpoint else None,"membership_type":row.membership_type,"port_mode":row.port_mode,"evidence":row.evidence,"confidence":row.confidence_score,"confidence_level":confidence_level(row.confidence_score),"confidence_explanation":row.confidence_explanation,"first_observed_at":row.first_observed_at,"last_observed_at":row.last_observed_at,"state":"current" if row.is_current else "stale"})
        return {**self._item(segment),"memberships":memberships}

    def device_vlan(self, device_id):
        if not self._scoped_device(device_id): raise HTTPException(404,"Device was not found.")
        rows=self.db.scalars(select(VLANMembershipObservation).where(VLANMembershipObservation.connected_device_id==device_id).order_by(VLANMembershipObservation.is_current.desc(),VLANMembershipObservation.last_observed_at.desc())).all()
        history=[]
        for row in rows:
            segment=self.db.get(NetworkSegment,row.network_segment_id); interface=self.db.get(SNMPInterface,row.interface_id); switch=self.db.get(Device,row.switch_device_id)
            history.append({"vlan":self._item(segment),"switch":self._device(switch),"interface":{"id":str(interface.id),"name":interface.name,"operational_status":interface.operational_status},"port_mode":row.port_mode,"evidence":row.evidence,"confidence":row.confidence_score,"confidence_level":confidence_level(row.confidence_score),"last_observed_at":row.last_observed_at,"state":"current" if row.is_current else "stale"})
        current=[x for x in history if x["state"]=="current"]
        return {"device_id":str(device_id),"current":current,"history":[x for x in history if x["state"]=="stale"],"data_state":"current" if current else "unknown","message":None if current else "VLAN membership is unknown or port-level VLAN information is unavailable."}

    def stats(self):
        rows=self.db.scalars(select(VLANMembershipObservation).where(VLANMembershipObservation.switch_device_id.in_(self._device_query()))).all(); segment_ids={x.network_segment_id for x in rows}; segments=self.db.scalars(select(NetworkSegment).where(NetworkSegment.id.in_(segment_ids),NetworkSegment.vlan_id.is_not(None))).all() if segment_ids else []; current=[x for x in rows if x.is_current]
        by_interface=defaultdict(set)
        for row in current: by_interface[row.interface_id].add(row.network_segment_id)
        return {"vlans_discovered":len(segments),"subnets_identified":len([x for x in segments if x.cidr]),"devices_with_vlan_information":len({x.connected_device_id for x in current if x.connected_device_id}),"ports_with_vlan_information":len({x.interface_id for x in current}),"trunk_ports":len({x.interface_id for x in current if x.port_mode=="trunk"}),"multi_vlan_relationships":len([values for values in by_interface.values() if len(values)>1]),"stale_vlan_relationships":len([x for x in rows if not x.is_current]),"unknown_vlan_relationships":len([x for x in current if not x.connected_device_id]),"duplicates":0}
