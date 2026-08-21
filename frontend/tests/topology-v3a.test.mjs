import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page=readFileSync(new URL("../src/pages/TopologyPage.tsx",import.meta.url),"utf8");
const details=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");

test("V3A topology is a protected, navigable workspace",()=>{
  assert.match(app,/lazy\(\(\) => import\("\.\/pages\/TopologyPage"\)\)/);
  assert.match(app,/path="\/topology"/);
  assert.match(sidebar,/label: ?"Topology"/);
  assert.match(sidebar,/nav-sublink/);
});

test("topology uses the real API graph and never embeds sample devices",()=>{
  for(const method of ["v3aTopology","refreshV3ATopology","v3aTopologyStats","v3aTopologyRelationship","v3aDeviceNeighbors"])assert.ok(api.includes(`${method}:`),method);
  assert.match(page,/from "@xyflow\/react"/);
  assert.match(page,/<ReactFlow/);
  assert.doesNotMatch(page,/10\.50\.|192\.168\.|mockNodes|sampleGraph|dummy/i);
});

test("empty, unavailable, stale, confidence and evidence states are visible",()=>{
  for(const phrase of ["Topology data unavailable","No connections found","Stale relationship","confidence_explanation","Evidence history","last_verified_at"])assert.ok(page.includes(phrase),phrase);
});

test("users can inspect neighbors and open the same inventory device",()=>{
  assert.match(page,/Immediate connections/);
  assert.match(page,/Open same inventory device/);
  assert.match(page,/to={`\/devices\/\$\{selectedNode\.device_id\}`}/);
  assert.match(details,/Network connections/);
  assert.match(details,/Open connected device/);
});

test("refresh is administrator controlled and topology remains observation-only",()=>{
  assert.match(page,/user\?\.role\s*===\s*"admin"/);
  assert.match(page,/Topology is observation-only/);
  assert.doesNotMatch(page,/change VLAN|restart device|configure port|manual link/i);
});
