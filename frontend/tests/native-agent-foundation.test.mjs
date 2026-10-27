import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync(new URL("../src/pages/LocalAgentsPage.tsx", import.meta.url), "utf8");
const deviceDetails = fs.readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx", import.meta.url), "utf8");
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

test("device actions are explicit and brokered RDP is not misrepresented", () => {
  assert.match(deviceDetails, /Restart device/);
  assert.match(deviceDetails, /Shut down device/);
  assert.match(deviceDetails, /Lock user session/);
  assert.match(deviceDetails, /Native RDP/);
  assert.match(deviceDetails, /createDeviceAgentAction/);
  assert.match(api, /createDeviceAgentAction/);
  assert.match(page, /Agent-brokered remote desktop is not available/);
  assert.match(page, /does not accept arbitrary commands/);
});

test("agent discoveries reconcile matches and keep unmatched devices in review", () => {
  assert.match(page, /network range containing the agent computer/);
  assert.match(page, /network range containing the agent computer/);
  assert.match(page, /unmatched or conflicting devices stay in Discovery for review/);
});
