import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page=fs.readFileSync(new URL("../src/pages/ReportingPage.tsx",import.meta.url),"utf8");
const app=fs.readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=fs.readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const api=fs.readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("reporting is a Manage workspace rather than a new primary pillar",()=>{
  assert.match(app,/path="\/reports"/);
  assert.match(sidebar,/label:\s*"Reports",\s*to:\s*"\/reports"/);
  assert.equal((sidebar.match(/label: "Overview"/g)||[]).length,1);
});

test("V4I exposes the fourteen focused report types",()=>{
  for(const report of ["executive","operations","network","assets","lifecycle","incidents","problems","changes","procurement","vendors","knowledge","services","departments","locations"]) assert.ok(page.includes(`"${report}"`));
});

test("date ranges, honest missing data, trends, drilldowns, and CSV export are visible",()=>{
  for(const value of ["Today","Last 7 days","Last 30 days","Last 90 days","This month","This quarter","This year","Custom range","Insufficient data","historical trend","Open underlying records","Export CSV"]) assert.ok(page.includes(value));
  assert.match(api,/\/reporting\/\$\{report\}/);
  assert.match(api,/export\.csv/);
});

test("the V4I surface has no predictive or generic BI builder capability",()=>{
  assert.doesNotMatch(page,/predictive|forecast|drag-and-drop|custom sql|multi-property|AI analytics/i);
});
