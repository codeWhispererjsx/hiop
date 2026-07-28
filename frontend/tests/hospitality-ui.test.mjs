import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const page = readFileSync(new URL("../src/pages/HospitalityPage.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const types = readFileSync(new URL("../src/lib/types.ts", import.meta.url), "utf8");

test("hospitality navigation and protected routes exist", () => {
  assert.match(app, /path="\/organizations"/);
  assert.match(app, /path="\/properties"/);
  assert.match(sidebar, /Organizations/);
  assert.match(sidebar, /Properties/);
  assert.match(app, /lazy\(\(\) => import\("\.\/pages\/HospitalityPage"\)\)/);
});

test("typed organization and property APIs and contracts exist", () => {
  for (const method of ["organizations", "properties", "createOrganization", "createProperty", "updateProperty", "archiveProperty"]) assert.match(api, new RegExp(`${method}:`));
  assert.match(types, /type Organization/);
  assert.match(types, /type Property/);
  assert.match(page, /Role-controlled management/);
});

test("property selector-ready directory supports search context and responsive states", () => {
  assert.match(types, /organization_id/);
  assert.match(page, /operational_status/);
  assert.match(page, /No properties configured yet/);
  assert.match(page, /No organizations configured yet/);
  assert.match(page, /role === "admin"/);
});
