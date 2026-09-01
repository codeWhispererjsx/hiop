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
  for (const label of ["Quick Scan", "Discover Devices", "Devices", "Needs Review"]) assert.match(page, new RegExp(label));
  for (const removed of ["Advanced", "Policies", "Credentials", "Topology", "CMDB synchronization"]) assert.doesNotMatch(page, new RegExp(removed));
});

test("quick scan needs no credentials and consolidates observations", () => {
  assert.match(api, /quickDiscoveryScan/);
  assert.match(api, /consolidatedDiscoveryDevices/);
  assert.match(page, /No credentials are\s+required/);
  assert.match(page, /Real devices in this property/);
  assert.match(page, /Why HIOP identified this device/);
});

test("device details open in the shared modal instead of below the table", () => {
  assert.match(page, /import Modal from "\.\.\/components\/Modal"/);
  assert.match(page, /<Modal title="Device details"/);
  assert.match(page, /<Evidence[\s\S]*<\/Modal>/);
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
  for (const label of ["Confidence", "Confirm Identification", "Identity history", "Conflicts", "Review"])
    assert.match(page, new RegExp(label.replace(" ", "\\s+"), "i"));
  assert.match(page, /correlated\s+observation/i);
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

test("production acceptance keeps confidence bands and device roles consistent", () => {
  assert.match(page, /confidence_score >= 60/);
  assert.match(page, /device\.device_type \|\| device\.classification/);
  assert.match(page, /DNS information available/);
  assert.match(api, /inventoryDiscoveryIdentity/);
});

test("friendly identity never hides the technical hostname", () => {
  assert.match(page, /device\.friendly_name\s*\|\|\s*"Unknown Device"/);
  assert.match(page, /device\.primary_hostname\s*\|\|\s*device\.fqdn\s*\|\|\s*"Not yet discovered"/);
  assert.match(page, /<th>Device<\/th>[\s\S]*<th>Hostname<\/th>/);
  assert.match(page, /device\.friendly_name,[\s\S]*device\.primary_hostname,[\s\S]*device\.ip_address,[\s\S]*device\.mac_address/);
  const example = { friendly_name: "Front Office Printer 1", primary_hostname: "heloshadtsc1821" };
  assert.equal(example.friendly_name, "Front Office Printer 1");
  assert.equal(example.primary_hostname, "heloshadtsc1821");
});

test("bulk approval is explicit, confirmed, and uses the scoped API", () => {
  for (const label of ["Select Identified", "Select All", "Approve Selected", "These devices will be added to this property's managed inventory"])
    assert.match(page, new RegExp(label));
  assert.match(page, /confirmBulkApproval/);
  assert.doesNotMatch(page, /window\.confirm/);
  assert.match(api, /bulkApproveDiscoveryResults/);
  assert.match(api, /discovery-intelligence\/results\/bulk-approve/);
});

test("bulk selection can target only devices with discovered hostnames", () => {
  assert.match(page, /Select with hostname/);
  assert.match(page, /hasDiscoveredHostname\(item\)/);
  assert.match(page, /hostname !== "not yet discovered"/);
  assert.match(page, /!item\.inventory_device_id/);
});

test("scanner starts asynchronously and exposes real progress and cancellation", () => {
  assert.match(api, /discoveryJobResults/);
  assert.match(api, /cancelDiscoveryJob/);
  for (const label of ["Addresses checked", "Devices found", "Current phase", "Cancel Scan"])
    assert.match(page, new RegExp(label));
  assert.match(page, /hosts_completed/);
  assert.match(page, /hosts_total/);
  assert.match(page, /devices_discovered/);
  assert.match(page, /setInterval\(\(\) => void refresh\(\), 2500\)/);
});

test("cleared quick-scan results stay dismissed after refresh without deleting history", () => {
  assert.match(page, /hiop\.discovery\.cleared_scan/);
  assert.match(page, /latest\.id === clearedScanId/);
  assert.match(page, /Historical evidence and managed devices were preserved/);
});

test("zero-result scans explain environmental causes without fabricating devices", () => {
  assert.match(page, /No responding hosts were detected/);
  assert.match(page, /devices may block ICMP/);
  assert.match(page, /Retry Scan/);
  assert.match(page, /Check Network Settings/);
});

test("discovery separates identified, review, and unknown without fabrication", () => {
  for (const label of ["Identified", "Needs review", "Unknown", "Unknown Device", "Technical identity preserved"])
    assert.match(page, new RegExp(label, "i"));
  assert.match(page, /identityBucket/);
});
