import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const details=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const backend=readFileSync(new URL("../../backend/app/main.py",import.meta.url),"utf8");

test("SNMP-dependent segmentation is not exposed as a live product surface",()=>{
  assert.doesNotMatch(app,/SegmentationPage|path="\/segmentation"/);
  assert.doesNotMatch(sidebar,/Segments/);
  assert.doesNotMatch(api,/\/segmentation\//);
  assert.doesNotMatch(backend,/segmentation_router/);
});
test("device details do not present unsupported port-derived segmentation",()=>{
  assert.doesNotMatch(details,/Network connection|Segmentation|VLAN Name|Gateway|Switch port/);
});
