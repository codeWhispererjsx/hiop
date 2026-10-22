import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const details=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const backend=readFileSync(new URL("../../backend/app/main.py",import.meta.url),"utf8");

test("port intelligence is not exposed by the app or device details",()=>{
  assert.doesNotMatch(app,/TopologyPage|SNMPPage/);
  assert.doesNotMatch(details,/v3b|port intelligence|switch port|VLAN|topology/i);
  assert.doesNotMatch(backend,/port_intelligence_router/);
});
