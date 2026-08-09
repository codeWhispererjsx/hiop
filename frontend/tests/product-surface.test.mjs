import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");

test("the operational pillars, V3A topology, and administration are navigable", () => {
  for (const label of ["Overview", "Discover", "Monitor", "Topology", "Manage", "Automate", "Maintain", "Administration"]) {
    assert.match(sidebar, new RegExp(`label: "${label}"`));
  }
  assert.match(app, /path="\/topology"/);
  for (const route of ["analytics", "assets", "business-intelligence", "changes", "cmdb", "knowledge", "problems", "reports", "snmp", "tickets"]) {
    assert.doesNotMatch(app, new RegExp(`path="/${route}`));
  }
});
