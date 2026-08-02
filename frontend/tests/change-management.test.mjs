import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const app=readFileSync("src/App.tsx","utf8"),sidebar=readFileSync("src/components/Sidebar.tsx","utf8"),page=readFileSync("src/pages/ChangeManagementPage.tsx","utf8"),api=readFileSync("src/lib/api.ts","utf8"),types=readFileSync("src/lib/types.ts","utf8"),css=readFileSync("src/styles/change-management.css","utf8");

test("change management protected route remains registered",()=>{assert.match(app,/ChangeManagementPage/);assert.match(app,/path="\/changes\/\*"/);assert.doesNotMatch(sidebar,/Change Management/)});
test("workspace exposes all requested operational views",()=>{for(const label of ["Dashboard","RFCs","New RFC","Approvals","CAB","Risk","Maintenance","Execution","Releases","Timeline","Reports","Audit"])assert.match(page,new RegExp(label,"i"))});
test("RFC workflow remains reviewed and deterministic",()=>{for(const value of ["Business justification","Technical justification","Implementation plan","Test plan","Validation plan","Communication plan","Backout plan","Start controlled execution"])assert.match(page,new RegExp(value,"i"));assert.doesNotMatch(page,/dangerouslySetInnerHTML|contentEditable|AI-generated|autonomous execution/i)});
test("CAB risk maintenance rollback release and exports use typed APIs",()=>{for(const method of ["changeDashboard","createChangeRequest","decideChangeApproval","changeRisk","createCABMeeting","cabVote","maintenanceWindows","startChangeExecution","requestChangeRollback","enterpriseReleases","exportChangeReport"])assert.match(api,new RegExp(method))});
test("aligned types cover core change entities",()=>{for(const name of ["ChangeRequest","ChangeApproval","ChangeRiskAssessment","CABMeeting","MaintenanceWindow","ChangeExecution","ChangeRollback","EnterpriseRelease","ChangeCommunication"])assert.match(types,new RegExp(`type ${name}`))});
test("workspace is responsive and uses existing theme tokens",()=>{assert.match(css,/@media\(max-width:820px\)/);assert.match(css,/var\(--/);assert.doesNotMatch(css,/#[0-9a-f]{3,8}/i)});
