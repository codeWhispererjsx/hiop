import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const page=readFileSync(new URL("../src/pages/KnowledgePage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");
const types=readFileSync(new URL("../src/lib/types.ts",import.meta.url),"utf8");
const app=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
const sidebar=readFileSync(new URL("../src/components/Sidebar.tsx",import.meta.url),"utf8");
const css=readFileSync(new URL("../src/styles/knowledge.css",import.meta.url),"utf8");

test("knowledge navigation and protected lazy route are registered",()=>{
  assert.match(app,/KnowledgePage/);assert.match(app,/\/knowledge\/\*/);assert.match(sidebar,/Knowledge & Runbooks/);
});

test("workspace exposes every Epic 3D operational view",()=>{
  for(const label of ["Articles","Runbooks","SOPs","Service Catalog","Documents","Troubleshooting","Checklists","Search","Approvals","Favorites","Recently Viewed","Reports"])assert.match(page,new RegExp(label));
});

test("article and runbook workflows remain structured and human controlled",()=>{
  for(const label of ["Markdown body","Submit review","Approve version","Complete manually","Evidence required"])assert.match(page,new RegExp(label));
  assert.doesNotMatch(page,/contentEditable|dangerouslySetInnerHTML/i);
  assert.match(page,/No AI summarization/i);
});

test("typed API covers knowledge, execution, search, relationships, and reports",()=>{
  for(const method of ["knowledgeArticles","knowledgeRevisions","runbooks","runbookExecutions","standardProcedures","serviceCatalogs","knowledgeDocuments","troubleshootingGuides","operationalChecklists","searchKnowledge","knowledgeRelationships","exportKnowledgeReport"])assert.match(api,new RegExp(method));
});

test("aligned types cover primary knowledge entities",()=>{
  for(const name of ["KnowledgeArticle","KnowledgeRevision","RunbookVersion","RunbookExecution","StandardProcedure","ServiceCatalog","KnowledgeDocument","TroubleshootingGuide","OperationalChecklistTemplate"])assert.match(types,new RegExp(`type ${name}`));
});

test("knowledge interface is responsive and theme-token based",()=>{
  assert.match(css,/@media\(max-width:720px\)/);assert.match(css,/var\(--surface\)/);assert.match(css,/overflow-x:auto/);
  assert.doesNotMatch(css,/#(?:[0-9a-f]{3}){1,2}/i);
});
