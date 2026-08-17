import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
const page=fs.readFileSync(new URL("../src/pages/OrganizationStructurePage.tsx",import.meta.url),"utf8");
const api=fs.readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
test("agent administration uses one-time enrollment and explicit property binding",()=>{
  assert.match(page,/Generate enrollment/);assert.match(page,/One-time token/);assert.match(page,/property_id/);assert.match(api,/local-agents\/enrollments/);
});
test("agent administration exposes health and revocation without secrets",()=>{
  assert.match(page,/Heartbeat:/);assert.match(page,/Queue:/);assert.match(page,/Revoke/);assert.doesNotMatch(page,/credential_hash|credential_expires_at/);
});
