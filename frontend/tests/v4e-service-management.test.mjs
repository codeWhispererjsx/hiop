import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page=fs.readFileSync(new URL("../src/pages/IncidentsPage.tsx",import.meta.url),"utf8");
const api=fs.readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
const asset=fs.readFileSync(new URL("../src/pages/AssetDetailsPage.tsx",import.meta.url),"utf8");

test("Maintain exposes incidents and technology services without a new top-level module",()=>{
  assert.match(page,/Maintain workspaces/);assert.match(page,/to="\/incidents\/services"/);assert.match(page,/No technology services configured yet/);
});
test("incident operational lifecycle is available",()=>{
  for(const value of ["new","acknowledged","in_progress","on_hold","resolved","closed"])assert.match(page,new RegExp(value));
  assert.match(page,/Resolution summary/);assert.match(page,/Closure notes/);assert.match(page,/Reopen/);
});
test("incident business context includes service asset vendor procurement and impact",()=>{
  for(const value of ["Service","Asset","Vendor","Support contact","Procurement","Impact"])assert.match(page,new RegExp(value));
});
test("service management API is separate from alert and legacy incident APIs",()=>{
  for(const route of ["/service-management/summary","/service-management/incidents","/service-management/services"])assert.ok(api.includes(route));
});
test("existing and automatic tickets can be assigned to eligible property technicians",()=>{
  assert.match(page,/Assign technician/);assert.match(page,/Only active IT Technicians with access to this property/);
  assert.match(page,/assignServiceIncident/);assert.match(api,/\/assignees/);assert.match(api,/\/assign/);
});
test("asset details show linked incident history",()=>{
  assert.match(asset,/assetIncidentHistory/);assert.match(asset,/Incident history/);assert.match(asset,/to={`\/incidents\/\${item.id}`}/);
});
