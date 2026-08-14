import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");

test("the sidebar keeps seven primary pillars and exposes focused submenus", () => {
  for (const label of ["Overview", "Discover", "Monitor", "Manage", "Automate", "Maintain", "Administration"]) {
    assert.match(sidebar, new RegExp(`label: "${label}"`));
  }
  for (const label of ["Alerts", "Topology", "Segments", "Users", "Roles & access", "Audit log", "Settings"]) {
    assert.match(sidebar, new RegExp(`label: ?"${label}"`));
  }
  assert.match(sidebar, /nav-sublink/);
  assert.match(app, /path="\/topology"/);
  for (const route of ["analytics", "business-intelligence", "cmdb", "snmp", "tickets"]) {
    assert.doesNotMatch(app, new RegExp(`path="/${route}`));
  }
});
