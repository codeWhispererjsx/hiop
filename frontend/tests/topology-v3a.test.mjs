import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const details=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const backend=readFileSync(new URL("../../backend/app/main.py",import.meta.url),"utf8");
const discovery=readFileSync(new URL("../../backend/app/api/v1/discovery_intelligence.py",import.meta.url),"utf8");

test("topology is not exposed in application routes, navigation, or device details",()=>{
  assert.doesNotMatch(app,/TopologyPage|path="\/topology"/);
  assert.doesNotMatch(sidebar,/label: ?"Topology"/);
  assert.doesNotMatch(details,/topology|Network connections/i);
  assert.doesNotMatch(backend,/topology_v3a_router|port_intelligence_router/);
  assert.doesNotMatch(discovery,/Topology|topology|SNMP|snmp/);
});
