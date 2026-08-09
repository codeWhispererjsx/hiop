import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const app = read("src/App.tsx");
const sidebar = read("src/components/Sidebar.tsx");
const page = read("src/pages/DiscoveryIntelligencePage.tsx");
const api = read("src/lib/api.ts");
const settings = read("src/pages/SettingsPage.tsx");
const activeDirectorySettings = read("src/components/ActiveDirectorySettings.tsx");

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

test("device details expose manual SNMP enrichment without cluttering the table", () => {
  assert.match(api, /enrichDiscoveryResult/);
  for (const label of ["Enrich Device", "SNMP:", "Serial Number", "Firmware", "Uptime", "Interfaces"])
    assert.match(page, new RegExp(label));
});

test("V2C exposes read-only Active Directory configuration and device enrichment", () => {
  assert.match(settings, /Active Directory/);
  for (const label of ["LDAPS server", "Bind password", "Test connection", "only reads computer attributes"])
    assert.match(activeDirectorySettings, new RegExp(label, "i"));
  assert.match(api, /enrichDiscoveryResultFromAD/);
  for (const label of ["Enrich from Active Directory", "Windows \/ Active Directory", "Distinguished Name", "Suggested Department"])
    assert.match(page, new RegExp(label));
  assert.doesNotMatch(page, /create users|move computers|group membership/i);
});

test("V2D exposes correlation confidence conflicts history and manual confirmation", () => {
  assert.match(api, /confirmDiscoveryIdentity/);
  for (const label of ["Confidence", "Confirm Identification", "Identity history", "Conflicts", "correlated observation", "Review"])
    assert.match(page, new RegExp(label, "i"));
  assert.match(page, /conflict_status/);
  assert.match(page, /confidence_level/);
});

test("V2E presents a technician-friendly final discovery experience", () => {
  for (const label of ["Friendly Name", "Original Hostname", "Identification confidence", "Technical", "Identity history", "Approve Device"])
    assert.match(page, new RegExp(label, "i"));
  for (const searchable of ["departmentFilter", "typeFilter", "vendorFilter", "mac_address"])
    assert.match(page, new RegExp(searchable));
  for (const state of ["No devices discovered yet", "Enrichment has not been performed", "SNMP unavailable", "Active Directory unavailable", "DNS information unavailable"])
    assert.match(page, new RegExp(state));
  assert.match(page, /inventory_device_id/);
  assert.doesNotMatch(page, /\+\{String\(item\.weight/);
});
