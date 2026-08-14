import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page=fs.readFileSync(new URL("../src/pages/OrganizationStructurePage.tsx",import.meta.url),"utf8");
const app=fs.readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=fs.readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const api=fs.readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("organization configuration lives under Administration, not a new top-level module",()=>{
  assert.match(app,/\/administration\/organization/);
  assert.match(sidebar,/Organization.*\/administration\/organization/);
  assert.doesNotMatch(sidebar,/label: ?"Local Agent"/);
});
test("organization workspace manages general details, departments, locations and passive agents",()=>{
  for(const value of ["general","departments","locations","agents","Save organization","Add department","Add location","Register agent identity"])assert.ok(page.includes(value));
  assert.match(page,/does not expose remote commands or auto-updates/);
});
test("frontend uses tenant-aware organization structure APIs",()=>{
  for(const route of ["/organization-structure/organization","/organization-structure/departments","/organization-structure/locations","/organization-structure/agents"])assert.ok(api.includes(route));
});
