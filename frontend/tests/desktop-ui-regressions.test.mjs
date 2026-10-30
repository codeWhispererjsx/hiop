import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = (path) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("Site Server diagnostics anchors are not overridden by route scroll reset", () => {
  const layout = source("../src/layouts/DashboardLayout.tsx");
  assert.match(layout, /if \(location\.hash\) return;\s+const resetScroll/);
  assert.match(source("../src/pages/ThisComputerPage.tsx"), /id="diagnostics"/);
});

test("performance resolves device names across every API page and avoids UUID link styling", () => {
  const page = source("../src/pages/NetworkPerformancePage.tsx");
  const api = source("../src/lib/api.ts");
  const styles = source("../src/styles/network-performance.css");
  assert.match(page, /devices\.total_pages/);
  assert.match(page, /performance-device-link/);
  assert.match(page, /performance-table-wrap/);
  assert.match(page, /"Unidentified device"/);
  assert.match(styles, /\.performance-table-wrap\{[^}]*overflow-x:auto/);
  assert.match(styles, /\.performance-table-wrap table\{[^}]*width:max\(100%,900px\)/);
  assert.match(api, /devices: \(filters:/);
});

test("inventory exports include imported assigned-to data", () => {
  assert.match(source("../src/pages/DevicesPage.tsx"), /\["Assigned to", "business_owner"\]/);
});

test("import conflict cards keep match details and actions in explicit responsive grid areas", () => {
  const page = source("../src/components/imports/ImportSteps.tsx");
  const styles = source("../src/styles/inventory-imports.css");
  const responsiveStyles = styles.split("@media (max-width: 1100px)")[1]?.split("@media (max-width: 600px)")[0] ?? "";
  assert.match(page, /className="match-candidate"/);
  assert.match(styles, /\.review-card\s*\{[^}]*grid-template-columns:\s*24px minmax\(170px, \.85fr\) minmax\(280px, 1\.2fr\) minmax\(245px, auto\)/s);
  assert.match(styles, /\.match-candidate\s*\{[^}]*display:\s*grid/s);
  assert.match(styles, /\.import-row-actions\s*\{[^}]*flex-wrap:\s*nowrap/s);
  assert.match(responsiveStyles, /\.import-row-actions \{[^}]*flex-wrap: wrap/s);
});

test("desktop operations, organization, and alert rules use the repaired layouts", () => {
  assert.match(source("../src/pages/ThisComputerPage.tsx"), /site-server-donut/);
  assert.match(source("../src/pages/OrganizationStructurePage.tsx"), /organization-table-wrap/);
  assert.match(source("../src/pages/AdministrationPage.tsx"), /admin-roles/);
  assert.match(source("../src/pages/AlertsPage.tsx"), /alert-rule-card/);
  assert.match(source("../src/pages/DiscoveryIntelligencePage.tsx"), /discovery-guidance-card/);
});
