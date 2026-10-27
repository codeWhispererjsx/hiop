import test from "node:test";import assert from "node:assert/strict";import{readFileSync}from"node:fs";
const page=readFileSync(new URL("../src/pages/AlertsPage.tsx",import.meta.url),"utf8");const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");const nav=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");const monitor=readFileSync(new URL("../src/pages/NetworkPage.tsx",import.meta.url),"utf8");
test("V3E alert center separates alerts events and rules",()=>{for(const text of ["Alerts & events","Alerts","Events","Rules","Acknowledge","Resolve manually","Alert history"])assert.ok(page.includes(text));assert.match(nav,/Alerts.*\/alerts/);assert.match(nav,/nav-sublink/);assert.match(monitor,/to="\/alerts"/)});
test("V3E uses explicit lifecycle and administrative APIs",()=>{for(const path of ["alert-center/alerts","alert-center/events","alert-center/rules","alert-center/notifications"])assert.ok(api.includes(path));});
test("alert acknowledgement and resolution surface failures to users",()=>{
  assert.match(page,/The alert could not be acknowledged/);
  assert.match(page,/The alert could not be resolved/);
  assert.match(page,/role="alert"/);
});
test("rules loading, failures, and the API response shape are handled",()=>{
  assert.match(api,/v3Rules|v3eRules:\(\)=>api<\{items:/);
  assert.match(page,/rules\.data\?\.items/);
  assert.match(page,/rules may not have been installed/);
  assert.match(page,/onRetry=\{reload\}/);
});
