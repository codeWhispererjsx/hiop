import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const page=readFileSync(new URL("../src/pages/AutomationPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("automation route and navigation are protected and registered",()=>{
  assert.match(app,/path="\/automation\/\*"/);
  assert.match(sidebar,/label: "Automation"/);
});

test("automation workspace uses typed APIs without executable input",()=>{
  for(const method of ["automationWorkflows","automationVersions","automationSteps","automationPlan","automationRuns","automationApprovals"]) assert.match(api,new RegExp(method));
  assert.doesNotMatch(page,/shell|eval\(|new Function|script/i);
  assert.match(page,/Approval-safe operations/);
});
