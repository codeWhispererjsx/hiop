import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const page=readFileSync(new URL("../src/pages/AutomationPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("automation route and navigation are protected and registered",()=>{
  assert.match(app,/path="\/automation\/\*"/);
  assert.match(sidebar,/label: "Automate"/);
});

test("automation workspace uses typed APIs without executable input",()=>{
  for(const method of ["automationWorkflows","automationVersions","automationSteps","automationPlan","automationRuns","automationApprovals","automationTriggers","validateAutomationTrigger","automationSchedules","runAutomationSchedule","automationEvents","automationEventCatalogue","automationSchedulerStatus","automationCorrelationGroups","automationDeadLetters","automationRetentionPreview","automationReportSummary"]) assert.match(api,new RegExp(method));
  assert.doesNotMatch(page,/eval\(|new Function|type=["']?script|name=["']?(shell|script)/i);
  assert.match(page,/Approval-safe operations/);
  assert.match(page,/New schedules and triggers are disabled or approval-gated by default/);
  assert.match(page,/Internal event explorer/);
  assert.match(page,/Run now/);
  assert.match(page,/Schedule builder/);
  assert.match(page,/Correlation and dead-letter review/);
});
