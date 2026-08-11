import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
const page=readFileSync(new URL("../src/pages/AutomationPage.tsx",import.meta.url),"utf8");
test("automation settings expose daily audit delivery controls",()=>{
  for(const label of ["Daily audit log email","Daily audit delivery time","Recipient email"])assert.match(page,new RegExp(label));
  assert.match(page,/daily_audit_email/);assert.match(page,/daily_audit_time/);
});
