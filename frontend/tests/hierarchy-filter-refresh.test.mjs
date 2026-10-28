import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("all hierarchy create, edit, and deactivate actions publish the shared refresh event", () => {
  const hierarchyPage = source("../src/pages/HierarchyPage.tsx");
  assert.equal((hierarchyPage.match(/dispatchEvent\(new Event\("hiop:organization-updated"\)\)/g) ?? []).length, 2);
  assert.match(source("../src/pages/OrganizationStructurePage.tsx"), /dispatchEvent\(new Event\("hiop:organization-updated"\)\)/);
});

test("department and location filters use the live organization hierarchy catalog", () => {
  const devices = source("../src/pages/DevicesPage.tsx");
  const agents = source("../src/pages/LocalAgentsPage.tsx");
  const discovery = source("../src/pages/DiscoveryIntelligencePage.tsx");
  const reports = source("../src/pages/ReportingPage.tsx");
  const request = source("../src/hooks/useRequest.ts");

  for (const page of [devices, agents, discovery, reports]) {
    assert.match(page, /useRequest\(endpoints\.hierarchy, \[\]\)/);
  }
  assert.match(devices, /hierarchy\.data\?\.departments/);
  assert.match(devices, /hierarchy\.data\?\.rooms/);
  assert.match(devices, /departmentOptions\.includes\(department\) \? department : "All"/);
  assert.match(agents, /hierarchy\.data\?\.departments/);
  assert.match(agents, /hierarchy\.data\.buildings/);
  assert.match(discovery, /hierarchy\.data\?\.departments/);
  assert.match(reports, /All departments/);
  assert.match(reports, /All locations/);
  assert.match(request, /addEventListener\("hiop:organization-updated"/);
});
