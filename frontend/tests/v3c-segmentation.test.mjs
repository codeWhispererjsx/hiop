import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page=readFileSync(new URL("../src/pages/SegmentationPage.tsx",import.meta.url),"utf8");
const details=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("V3C exposes a simple operational VLAN segment view",()=>{
  for(const text of ["Network segmentation","VLANs","Subnets","Devices","Ports","Trunks","Unknown endpoints","Search network segmentation"]) assert.match(page,new RegExp(text));
  assert.match(page,/read-only/i);
});
test("device and switch details retain connection while adding segmentation",()=>{
  for(const text of ["Network connection","Segmentation","VLAN Name","Subnet","Gateway","Switch","Port","Evidence","VLANs"]) assert.match(details,new RegExp(text));
});
test("V3C frontend only calls read APIs plus deliberate refresh",()=>{
  assert.match(api,/segmentation\/vlans/);
  assert.match(api,/segmentation\/devices/);
  assert.match(api,/segmentation\/switches\/\$\{id\}\/refresh/);
  for(const forbidden of ["createVlan","deleteVlan","assignVlan","configureTrunk"]) assert.equal(api.includes(forbidden),false);
});
