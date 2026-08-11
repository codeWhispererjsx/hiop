import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const admin=readFileSync(new URL("../src/pages/AdministrationPage.tsx",import.meta.url),"utf8");
const users=readFileSync(new URL("../src/pages/UserDetailsPage.tsx",import.meta.url),"utf8");
const incidents=readFileSync(new URL("../src/pages/IncidentsPage.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");

test("administration explains the four-role policy and actual audit visibility",()=>{
  for(const text of ["Users","Settings","Roles and permissions","4 baseline roles","Administrative audit log","Organization Administrator"]) assert.match(admin,new RegExp(text));
});
test("administration is hidden from technician and viewer navigation",()=>{
  assert.match(sidebar,/isAdmin=role==="admin"/);
  assert.match(sidebar,/adminOnly/);
  assert.doesNotMatch(sidebar,/superOnly|superadmin/);
});
test("self role changes and viewer incident creation are absent from permission UX",()=>{
  assert.match(users,/!isOwnAccount&&<button[^>]*>.*Change role/);
  assert.match(incidents,/Viewer access is read-only/);
  assert.match(incidents,/canOperate\?<button[^>]*.*Create incident/);
});
