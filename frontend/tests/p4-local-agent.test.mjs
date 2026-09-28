import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
const page=fs.readFileSync(new URL("../src/pages/OrganizationStructurePage.tsx",import.meta.url),"utf8");
const localService=fs.readFileSync(new URL("../src/pages/ThisComputerPage.tsx",import.meta.url),"utf8");
test("desktop organization administration does not duplicate a local agent",()=>{
  assert.doesNotMatch(page,/Create connection code|Download Windows ZIP|Connect local agent/);
  assert.match(localService,/does not need a separate agent download/i);
});
