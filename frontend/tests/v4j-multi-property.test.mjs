import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
const app=fs.readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=fs.readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const header=fs.readFileSync(new URL("../src/components/Header.tsx",import.meta.url),"utf8");
const layout=fs.readFileSync(new URL("../src/layouts/DashboardLayout.tsx",import.meta.url),"utf8");
const page=fs.readFileSync(new URL("../src/pages/PropertiesPage.tsx",import.meta.url),"utf8");
const api=fs.readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("V4J property management remains inside Administration",()=>{assert.match(app,/administration\/properties/);assert.match(sidebar,/label:\s*"Properties"/);const primary=sidebar.slice(sidebar.indexOf("const primaryLinks"),sidebar.indexOf("const monitorLinks"));assert.doesNotMatch(primary,/label:\s*"Properties"/)});
test("active property context is visible and switching refreshes all scoped data",()=>{assert.match(header,/Current property/);assert.match(header,/All properties/);assert.match(layout,/hiop\.active_property_id/);assert.match(layout,/window\.location\.reload/);assert.match(api,/X-HIOP-Property-ID/)});
test("property administration exposes health comparison and access",()=>{for(const value of ["Add property","Assign property access","Availability","Open incidents","Health","Deactivate"])assert.ok(page.includes(value))});
test("property APIs are focused and no V5 capability is exposed",()=>{for(const route of ["/property-management/context","/property-management/comparison","/property-management/${id}/access"])assert.ok(api.includes(route));assert.doesNotMatch(page,/billing|subscription|predictive|AI\/AIOps|automated remediation/i)});
