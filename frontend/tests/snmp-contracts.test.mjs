import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const page = readFileSync(new URL("../src/pages/SNMPPage.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const types = readFileSync(new URL("../src/lib/types.ts", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");

test("SNMP route and authorized navigation are registered", () => {
  assert.match(app, /path="\/snmp\/\*"/);
  assert.match(sidebar, /SNMP Monitoring/);
  assert.match(page, /Read-only monitoring/);
});

test("secrets are write-only form values and never persisted by SNMP UI", () => {
  assert.match(page, /type="password"/);
  assert.doesNotMatch(page, /localStorage|sessionStorage/);
  assert.doesNotMatch(page, /community_encrypted|authentication_secret_encrypted|privacy_secret_encrypted/);
  assert.match(api, /rotateSNMPSecret/);
});

test("manual collection is allow-listed and has no raw OID request", () => {
  for (const group of ["availability", "system", "interface_inventory", "interface_performance", "device_performance", "all_profile_metrics"]) {
    assert.ok(page.includes(`"${group}"`));
  }
  assert.doesNotMatch(api, /arbitraryOid|rawOid|walkSNMP/);
});

test("typed client covers monitoring and review surfaces", () => {
  for (const method of ["snmpCredentials", "snmpTargets", "testSNMPTarget", "collectSNMPTarget", "snmpPollRuns", "snmpCandidates", "snmpInterfaces", "snmpMetrics", "snmpStateChanges", "snmpRetentionPreview"]) {
    assert.ok(api.includes(`${method}:`), method);
  }
  for (const type of ["SNMPCredential", "SNMPTarget", "SNMPMetric", "SNMPInterface", "SNMPStateChange", "SNMPMatchCandidate"]) {
    assert.ok(types.includes(`type ${type}`), type);
  }
});

test("accessible chart fallback and deliberate empty states exist", () => {
  assert.match(page, /role="img"/);
  assert.match(page, /className="sr-only"/);
  assert.match(page, /No metric samples|No numeric samples|No state changes/);
});
