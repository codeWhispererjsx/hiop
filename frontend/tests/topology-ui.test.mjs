import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const page = readFileSync(new URL("../src/pages/TopologyPage.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const types = readFileSync(new URL("../src/lib/types.ts", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles/topology.css", import.meta.url), "utf8");

test("topology navigation and lazy protected route are registered", () => {
  assert.match(app, /path="\/topology\/\*"/);
  assert.doesNotMatch(sidebar, /Network Topology/);
  assert.match(app, /lazy\(\(\) => import\("\.\/pages\/TopologyPage"\)\)/);
});

test("React Flow is the single interactive graph implementation", () => {
  assert.match(page, /from "@xyflow\/react"/);
  assert.match(page, /<ReactFlow/);
  for (const capability of ["Background", "Controls", "MiniMap", "nodesDraggable", "fitView"]) {
    assert.ok(page.includes(capability), capability);
  }
  assert.doesNotMatch(page, /cytoscape|sigma\.js|d3-force/);
});

test("typed topology client covers graph and review workflows", () => {
  for (const method of [
    "topologies", "topologyGraph", "topologyStats", "saveTopologyLayout",
    "topologyPath", "topologyImpact", "topologyConflicts", "topologyReviewItems",
    "runTopologyInference", "topologyCandidateLinks", "topologySnapshots",
    "topologySnapshotGraph", "compareTopologySnapshot", "topologyChanges",
  ]) assert.ok(api.includes(`${method}:`), method);
  for (const name of [
    "TopologyGraph", "TopologyNode", "TopologyLink", "TopologyConflict",
    "TopologyReviewItem", "TopologyPath", "TopologyImpact", "TopologySnapshot",
    "SnapshotComparison", "TopologyFilterState", "TopologyGraphEvent",
  ]) assert.ok(types.includes(`type ${name}`), name);
});

test("map includes bounded layouts, filtering, path, impact, and snapshots", () => {
  for (const value of [
    "hierarchical", "force", "grid", "radial", "manual", "Path", "Impact",
    "Run inference", "Manual link", "Snapshot", "confidence_minimum",
  ]) assert.ok(page.includes(value), value);
  assert.match(page, /graph\.metadata\.bounded/);
  assert.match(page, /URLSearchParams/);
});

test("review mutations remain admin-only and confirmation protected", () => {
  assert.match(page, /user\?\.role==="admin"/);
  assert.match(page, /Approve and apply this reviewed topology change/);
  assert.match(page, /Run bounded topology inference now/);
  assert.match(page, /Source and target must be different/);
});

test("accessible fallback, responsive drawer, themes, and reduced motion exist", () => {
  assert.match(page, /Accessible graph table/);
  assert.match(page, /aria-label="Topology map controls"/);
  assert.match(page, /potentially affected/i);
  assert.match(css, /@media\(max-width:820px\)/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /var\(--topo-panel/);
});

test("no dummy graph or real infrastructure data is embedded", () => {
  assert.doesNotMatch(page, /192\.168\.|10\.\d+\.\d+\.\d+|hotel[-_ ]?(switch|router|firewall)/i);
  assert.doesNotMatch(page, /const\s+(mock|dummy|sample)(Nodes|Links|Graph)/i);
});

test("scheduled topology operations remain bounded and administrator controlled", () => {
  for (const method of [
    "topologySchedule", "updateTopologySchedule", "pauseTopologySchedule",
    "topologySchedulerStatus", "topologyHealth", "topologyOperationalRuns",
    "topologyAlertRules", "previewTopologyAlertRule", "topologyRetentionPreview",
    "runTopologyRetentionCleanup", "exportTopologyCsv",
  ]) assert.match(api, new RegExp(`${method}:`));
  assert.match(page, /Enable topology scheduler/);
  assert.match(page, /Maximum targets per run/);
  assert.match(page, /Start maintenance/);
  assert.match(page, /Protected baselines and audit history are excluded from cleanup/);
  assert.match(page, /user\?\.role!=="admin"/);
  assert.doesNotMatch(page, /arbitrary OID/i);
});
