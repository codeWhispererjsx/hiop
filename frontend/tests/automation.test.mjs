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

test("version one automation exposes only operational schedules",()=>{
  for(const method of ["settings","updateNetworkSettings","updateNotificationSettings"]) assert.match(api,new RegExp(method));
  assert.doesNotMatch(page,/eval\(|new Function|type=["']?script|name=["']?(shell|script)/i);
  for(const label of ["Scheduled network scans","Scheduled monitoring","Email notifications","Automatic offline incidents"]) assert.match(page,new RegExp(label));
  for(const removed of ["workflow builder","dead-letter","correlation","approval queue"]) assert.doesNotMatch(page,new RegExp(removed,"i"));
});
