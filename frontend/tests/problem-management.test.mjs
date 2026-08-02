import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const app=fs.readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=fs.readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const page=fs.readFileSync(new URL("../src/pages/ProblemManagementPage.tsx",import.meta.url),"utf8");
const api=fs.readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
const css=fs.readFileSync(new URL("../src/styles/problem-management.css",import.meta.url),"utf8");

test("Problem Management route and navigation are protected and registered",()=>{assert.match(app,/ProblemManagementPage/);assert.match(app,/path="\/problems\/\*"/);assert.match(sidebar,/Problem Management/)});
test("workspace exposes requested operational views",()=>{for(const label of ["Dashboard","Problems","RCA Workspace","5 Whys","Fishbone","Known Errors","Workarounds","CAPA","Reviews","Correlations","Relationships","Reports"])assert.match(page,new RegExp(label))});
test("typed client covers deterministic lifecycle and exports",()=>{for(const call of ["problemDashboard","transitionProblem","problemRCA","saveFiveWhy","addFishboneCause","knownErrors","createProblemPlan","detectProblemCorrelations","problemRelationshipGraph","exportProblemReport"])assert.match(api,new RegExp(call))});
test("responsive UI and human-control language are explicit",()=>{assert.match(css,/@media\(max-width:560px\)/);assert.match(page,/No root cause or resolution is generated automatically/);assert.match(page,/review suggestions only/)});
