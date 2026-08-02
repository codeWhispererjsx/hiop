import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const page=readFileSync(new URL("../src/pages/IncidentsPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");

test("incident command routes and navigation are registered",()=>{
  assert.match(app,/\/incidents\/:id\/\*/);
  assert.match(app,/\/incidents\/playbooks/);
  assert.match(sidebar,/label: "Maintain"/);
});

test("incident workspace includes tasks evidence remediation recovery and timeline",()=>{
  for(const label of ["Tasks and checklist","Evidence and communications","Playbook and reviewed remediation","Decisions and timeline","Verify recovery"]){
    assert.match(page,new RegExp(label));
  }
});

test("playbook builder is structured and does not expose a code editor",()=>{
  assert.match(page,/Structured playbook builder/);
  assert.match(page,/No code editor/);
  assert.doesNotMatch(page,/contentEditable/);
});

test("typed API client covers incident operations",()=>{
  for(const method of ["createIncident","incidentTransition","incidentTasks","incidentEvidence","incidentCommunications","incidentPlaybooks","startIncidentPlaybook","verifyIncidentRecovery"]){
    assert.match(api,new RegExp(method));
  }
});
