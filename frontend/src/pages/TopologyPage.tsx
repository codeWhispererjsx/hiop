import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints } from "../lib/api";
import type {
  User,
  V3ATopologyGraph,
  V3ATopologyNode,
  V3ATopologyRelationship,
  V3ATopologyStats,
} from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/topology-v3a.css";

const readable = (value: string) =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());

const when = (value: string) => new Date(value).toLocaleString();

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Topology could not be loaded.";

export default function TopologyPage() {
  const [graph, setGraph] = useState<V3ATopologyGraph>();
  const [stats, setStats] = useState<V3ATopologyStats>();
  const [user, setUser] = useState<User>();
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedNode, setSelectedNode] = useState<V3ATopologyNode>();
  const [selectedRelationship, setSelectedRelationship] =
    useState<V3ATopologyRelationship>();

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextGraph, nextStats, nextUser] = await Promise.all([
        endpoints.v3aTopology(search),
        endpoints.v3aTopologyStats(),
        endpoints.me(),
      ]);
      setGraph(nextGraph);
      setStats(nextStats);
      setUser(nextUser);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, search]);

  const refresh = async () => {
    setRefreshing(true);
    setNotice("");
    try {
      const result = await endpoints.refreshV3ATopology();
      setNotice(
        result.message +
          (result.targets_failed
            ? ` ${result.targets_failed} target(s) were unavailable.`
            : "")
      );
      await load();
    } catch (caught) {
      setNotice(errorMessage(caught));
    } finally {
      setRefreshing(false);
    }
  };

  const canvas = useMemo(() => layoutGraph(graph), [graph]);
  const selectedConnections = useMemo(
    () =>
      selectedNode && graph
        ? graph.relationships.filter(
            (link) =>
              link.source_node_id === selectedNode.id ||
              link.destination_node_id === selectedNode.id
          )
        : [],
    [graph, selectedNode]
  );

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Version 3 · Network intelligence"
        title="Network topology"
        copy="Evidence-backed connections between existing HIOP devices. Topology is observation-only."
        action={
          <div className="page-actions">
            <button
              className="secondary-action"
              onClick={() => void load()}
              disabled={loading}
              aria-label="Reload topology view"
            >
              <Icon name="network" aria-hidden="true" />
              Reload view
            </button>
            {user?.role === "admin" && (
              <button
                className="primary-action"
                onClick={() => void refresh()}
                disabled={refreshing}
                aria-label="Refresh topology data"
                aria-busy={refreshing}
              >
                <Icon name="discovery" aria-hidden="true" />
                {refreshing ? "Identifying connections…" : "Refresh topology"}
              </button>
            )}
          </div>
        }
      />
      <section className="operational-guide" aria-label="How network topology works">
        <div><span>What it shows</span><strong>Observed device-to-device relationships</strong><p>HIOP combines discovered neighbors, switches, ports, and confidence evidence into this live operational map.</p></div>
        <div><span>How to use it</span><strong>Refresh, select, inspect</strong><p>Administrators refresh evidence, then select a node or connection to inspect its source, confidence, port, and inventory record.</p></div>
        <div><span>Safety</span><strong>Observation only</strong><p>This page reads current evidence. It never changes a switch, VLAN, firewall rule, or production device.</p></div>
      </section>
      {notice && (
        <div className="topology-v3a-notice" role="status" aria-live="polite">
          {notice}
        </div>
      )}
      {stats && (
        <section className="topology-v3a-kpis" aria-label="Topology summary">
          <Kpi label="Relationships" value={stats.topology_relationships} />
          <Kpi label="Devices represented" value={stats.devices_represented} />
          <Kpi label="Verified" value={stats.relationships_verified} />
          <Kpi label="Stale" value={stats.stale_relationships} />
          <Kpi label="Unresolved evidence" value={stats.unresolved_relationships} />
          <Kpi label="Network devices" value={stats.network_devices ?? 0} />
          <Kpi label="End devices" value={stats.end_devices ?? 0} />
          <Kpi label="Confidence avg" value={`${stats.average_confidence ?? 0}%`} />
          <Kpi label="Active polls" value={stats.active_snmp_polls ?? 0} />
          <Kpi label="Failed polls" value={stats.failed_snmp_polls ?? 0} />
          <Kpi label="Avg response time" value={`${stats.average_response_time_ms ?? 0}ms`} />
          <Kpi label="Data freshness" value={`${stats.data_freshness_minutes ?? 0}m`} />
        </section>
      )}
      <section className="topology-v3a-toolbar" aria-label="Topology controls">
        <label htmlFor="topology-search">
          <Icon name="search" aria-hidden="true" />
          <span className="sr-only">Search topology</span>
          <input
            id="topology-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search hostname, IP, type or vendor"
            aria-label="Search topology by hostname, IP, type or vendor"
          />
        </label>
        <div aria-label="Legend">
          <span>
            <i className="online" aria-hidden="true" />
            Online device
          </span>
          <span>
            <i className="offline" aria-hidden="true" />
            Offline device
          </span>
          <span>
            <b aria-hidden="true" />
            Known relationship
          </span>
          <span>
            <b className="stale" aria-hidden="true" />
            Stale relationship
          </span>
        </div>
      </section>
      {loading && !graph || error ? (
        <Feedback
          loading={loading && !graph}
          error={error || undefined}
          onRetry={() => void load()}
        />
      ) : !graph || graph.data_state === "unavailable" ? (
        <TopologyEmpty
          title="Topology data unavailable"
          copy={
            graph?.message ||
            "Configure linked SNMP targets, then refresh topology."
          }
        />
      ) : graph.data_state === "no_connections" ? (
        <TopologyEmpty
          title="No connections found"
          copy={
            graph.message ||
            "The configured sources returned no sufficiently reliable relationships."
          }
        />
      ) : (
        <section className="topology-v3a-workspace">
          <div
            className="topology-v3a-canvas"
            aria-label="Interactive network topology"
            role="region"
          >
            <ReactFlow
              nodes={canvas.nodes}
              edges={canvas.edges}
              fitView
              minZoom={0.2}
              maxZoom={1.8}
              nodesDraggable={false}
              nodesConnectable={false}
              onNodeClick={(_, node) => {
                setSelectedRelationship(undefined);
                setSelectedNode(
                  graph.nodes.find((item) => item.id === node.id)
                );
              }}
              onEdgeClick={(_, edge) =>
                void endpoints
                  .v3aTopologyRelationship(edge.id)
                  .then((value) => {
                    setSelectedNode(undefined);
                    setSelectedRelationship(value);
                  })
              }
            >
              <Background gap={28} />
              <MiniMap
                pannable
                zoomable
                nodeColor={(node) =>
                  String(node.style?.borderColor || "var(--color-primary)")
                }
              />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          <aside className="topology-v3a-inspector" aria-label="Topology inspector">
            {selectedNode ? (
              <>
                <header>
                  <span>Selected device</span>
                  <h2>{selectedNode.label}</h2>
                  <StatusBadge status={selectedNode.status} />
                </header>
                <dl>
                  <Fact label="Hostname" value={selectedNode.hostname} />
                  <Fact
                    label="IP address"
                    value={selectedNode.ip_address || "Unknown"}
                  />
                  <Fact
                    label="Device type"
                    value={selectedNode.device_type || "Unknown"}
                  />
                  <Fact label="Network role" value={selectedNode.role || "Unknown"} />
                  <Fact
                    label="Vendor / model"
                    value={`${selectedNode.vendor || "Unknown"} / ${
                      selectedNode.model || "Not available"
                    }`}
                  />
                  <Fact
                    label="Immediate connections"
                    value={String(selectedConnections.length)}
                  />
                </dl>
                <Link
                  className="primary-action"
                  to={`/devices/${selectedNode.device_id}`}
                >
                  Open same inventory device
                </Link>
                <ConnectionList
                  selectedNodeId={selectedNode.id}
                  links={selectedConnections}
                  graph={graph}
                  onSelect={setSelectedNode}
                />
              </>
            ) : selectedRelationship ? (
              <RelationshipDetails
                relationship={selectedRelationship}
                graph={graph}
              />
            ) : (
              <div className="topology-v3a-prompt">
                <Icon name="hierarchy" size={34} aria-hidden="true" />
                <h2>Select a device or connection</h2>
                <p>
                  Inspect immediate neighbors, evidence, confidence and
                  verification timestamps.
                </p>
              </div>
            )}
          </aside>
        </section>
      )}
    </DashboardLayout>
  );
}

function layoutGraph(
  graph?: V3ATopologyGraph
): { nodes: Node[]; edges: Edge[] } {
  if (!graph) return { nodes: [], edges: [] };

  const network = graph.nodes.filter((node) =>
    /(switch|router|firewall|gateway|access point)/i.test(node.device_type)
  );
  const endpoints = graph.nodes.filter((node) => !network.includes(node));

  const position = (
    node: V3ATopologyNode,
    index: number,
    row: number,
    total: number
  ) => ({
    id: node.id,
    position: {
      x: (index - (total - 1) / 2) * 240,
      y: row * 230,
    },
    data: {
      label: (
        <div className="topology-v3a-node">
          <strong>{node.label}</strong>
          <span>{node.ip_address || "IP unknown"}</span>
          <small>
            {readable(node.device_type || "unknown")} ·{" "}
            {readable(node.status || "unknown")}
          </small>
        </div>
      ),
    },
    style: {
      width: 190,
      borderRadius: 14,
      border: `2px solid ${
        /online/i.test(node.status)
          ? "var(--color-success)"
          : /offline/i.test(node.status)
          ? "var(--color-danger)"
          : "var(--border-strong)"
      }`,
      background: "var(--surface)",
      color: "var(--text)",
      boxShadow: "var(--shadow-md)",
    },
  });

  const nodes = [
    ...network.map((node, index) => position(node, index, 0, network.length)),
    ...endpoints.map((node, index) => position(node, index, 1, endpoints.length)),
  ];

  const edges = graph.relationships.map((link) => ({
    id: link.id,
    source: link.source_node_id,
    target: link.destination_node_id,
    label: `${
      link.source_port?.name || link.destination_port?.name
        ? `${link.source_port?.name || link.destination_port?.name} · `
        : ""
    }${link.vlan_id ? `VLAN ${link.vlan_id} · ` : ""}${readable(
      link.relationship_type
    )} · ${link.confidence}%`,
    animated: false,
    style: {
      stroke:
        link.state === "stale"
          ? "var(--color-warning)"
          : "var(--color-primary)",
      strokeWidth: 2,
      strokeDasharray: link.state === "stale" ? "7 6" : undefined,
    },
    labelStyle: {
      fill: "var(--text)",
      fontSize: 11,
      fontWeight: 600,
    },
  }));

  return { nodes, edges };
}

function RelationshipDetails({
  relationship,
  graph,
}: {
  relationship: V3ATopologyRelationship;
  graph: V3ATopologyGraph;
}) {
  const source = graph.nodes.find(
    (node) => node.id === relationship.source_node_id
  );
  const destination = graph.nodes.find(
    (node) => node.id === relationship.destination_node_id
  );
  const port = relationship.source_port || relationship.destination_port;

  return (
    <>
      <header>
        <span>Network relationship</span>
        <h2>
          {source?.label || "Unknown"} → {destination?.label || "Unknown"}
        </h2>
        <StatusBadge status={relationship.state} />
      </header>
      <dl>
        <Fact label="Relationship" value={readable(relationship.relationship_type)} />
        <Fact label="Switch port" value={port?.name || "Unknown"} />
        <Fact
          label="VLAN"
          value={
            relationship.vlan_id
              ? `${relationship.vlan_id}${
                  relationship.vlan_name ? ` · ${relationship.vlan_name}` : ""
                }`
              : "Unknown"
          }
        />
        <Fact
          label="Interface description"
          value={port?.description || "Not available"}
        />
        <Fact
          label="Port status"
          value={
            port
              ? `Admin ${readable(port.admin_status)} · Operational ${readable(
                  port.operational_status
                )}`
              : "Unknown"
          }
        />
        <Fact label="Evidence" value={readable(relationship.evidence_source)} />
        <Fact
          label="Confidence"
          value={`${relationship.confidence}% · ${relationship.confidence_level}`}
        />
        <Fact label="Why" value={relationship.confidence_explanation} />
        <Fact
          label="First discovered"
          value={when(relationship.first_discovered_at)}
        />
        <Fact
          label="Last verified"
          value={when(relationship.last_verified_at)}
        />
      </dl>
      {relationship.evidence?.length ? (
        <div className="topology-v3a-evidence">
          <h3>Evidence history</h3>
          {relationship.evidence.map((item, index) => (
            <article key={`${item.observed_at}-${index}`}>
              <strong>{readable(item.source)}</strong>
              <span>{item.value || readable(item.type)}</span>
              <small>
                {item.confidence}% · {when(item.observed_at)}
              </small>
            </article>
          ))}
        </div>
      ) : (
        <p>No additional evidence details are available.</p>
      )}
    </>
  );
}

function ConnectionList({
  selectedNodeId,
  links,
  graph,
  onSelect,
}: {
  selectedNodeId: string;
  links: V3ATopologyRelationship[];
  graph: V3ATopologyGraph;
  onSelect: (node: V3ATopologyNode) => void;
}) {
  if (!links.length) {
    return <p className="topology-v3a-none">No immediate connections found.</p>;
  }

  return (
    <div className="topology-v3a-connections">
      <h3>Immediate connections</h3>
      {links.map((link) => {
        const neighborId =
          link.source_node_id === selectedNodeId
            ? link.destination_node_id
            : link.source_node_id;
        const current = graph.nodes.find((node) => node.id === neighborId);
        return current ? (
          <button
            key={link.id}
            onClick={() => onSelect(current)}
            aria-label={`View neighbor ${current.label}`}
          >
            <strong>{current.label}</strong>
            <span>
              {readable(link.relationship_type)} · {link.confidence}%
            </span>
          </button>
        ) : null;
      })}
    </div>
  );
}

function TopologyEmpty({ title, copy }: { title: string; copy: string }) {
  return (
    <section className="topology-v3a-empty">
      <Icon name="hierarchy" size={42} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{copy}</p>
      <small>
        Existing inventory remains unchanged. HIOP never invents topology
        relationships.
      </small>
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: number | string }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
