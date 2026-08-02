import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const app = read("src/App.tsx");
const sidebar = read("src/components/Sidebar.tsx");
const page = read("src/pages/DiscoveryIntelligencePage.tsx");
const api = read("src/lib/api.ts");

test("discovery is a primary product pillar", () => {
  assert.match(app, /DiscoveryIntelligencePage/);
  assert.match(app, /discovery-intelligence\/\*/);
  assert.match(sidebar, /label: "Discover"/);
});

test("discovery exposes a simple three-step experience", () => {
  for (const label of ["Quick Scan", "Scan network", "Devices", "Needs Review"]) assert.match(page, new RegExp(label));
  for (const removed of ["Advanced", "Policies", "Credentials", "Topology", "CMDB synchronization"]) assert.doesNotMatch(page, new RegExp(removed));
});

test("quick scan needs no credentials and consolidates observations", () => {
  assert.match(api, /quickDiscoveryScan/);
  assert.match(api, /consolidatedDiscoveryDevices/);
  assert.match(page, /No credentials are required/);
  assert.match(page, /One row per device/);
  assert.match(page, /Why HIOP identified this device/);
});
