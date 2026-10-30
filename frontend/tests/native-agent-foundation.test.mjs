import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync(new URL("../src/pages/LocalAgentsPage.tsx", import.meta.url), "utf8");
const deviceDetails = fs.readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx", import.meta.url), "utf8");
const assetDetails = fs.readFileSync(new URL("../src/pages/AssetDetailsPage.tsx", import.meta.url), "utf8");
const maintenance = fs.readFileSync(new URL("../src/pages/SystemMaintenancePage.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const guide = fs.readFileSync(new URL("../src/components/FeatureGuide.tsx", import.meta.url), "utf8");
const sidebar = fs.readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");

test("local agent instructions use the native installer and tray enrollment", () => {
  assert.match(page, /Install HIOP Agent\.cmd/);
  assert.match(page, /Connect or enroll\.\.\./);
  assert.match(page, /No Python installation is required/);
  assert.match(guide, /HIOP Agent tray icon/);
  assert.match(sidebar, /Agents - Managed Endpoints/);
  assert.doesNotMatch(page, /Python 3\.12|Connect HIOP\.cmd/);
});

test("phase one sends audited notices without endpoint control actions", () => {
  assert.match(page, /createAgentNotice/);
  assert.match(page, /expires after 15 minutes/);
  assert.match(page, /Local policies; no remote controls/);
  assert.match(page, /Device Health/);
  assert.match(page, /End-of-day prompts/);
  assert.doesNotMatch(page, /runAction|Shutdown|Wake-on-LAN|Copy RDP/);
  assert.doesNotMatch(deviceDetails, /Restart device|Shut down device|Lock user session|Native RDP|createDeviceAgentAction/);
  assert.doesNotMatch(assetDetails, /ManagedAssetActions|createManagedAssetAgentAction/);
  assert.doesNotMatch(api, /createDeviceAgentAction|createManagedAssetAgentAction|wakeDevice/);
  assert.match(maintenance, /scheduled controls are disabled/i);
});

test("agent discoveries reconcile matches and keep unmatched devices in review", () => {
  assert.match(page, /network range containing the agent computer/);
  assert.match(page, /network range containing the agent computer/);
  assert.match(page, /unmatched or conflicting devices stay in Discovery for review/);
});
