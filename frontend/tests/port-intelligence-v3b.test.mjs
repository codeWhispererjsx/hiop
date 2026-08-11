import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const details=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const topology=readFileSync(new URL("../src/pages/TopologyPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("V3B uses dedicated cached read APIs and an explicit administrator refresh",()=>{
  for(const method of ["v3bDeviceConnection","v3bSwitchInterfaces","v3bInterface","refreshV3BSwitch"])assert.ok(api.includes(`${method}:`),method);
  assert.match(api,/port-intelligence/);
});

test("device details show exact switch port status evidence and confidence without redesign",()=>{
  for(const phrase of ["Connected switch","Administrative status","Operational status","Last verified","Confidence","Evidence","Port: Unknown"])assert.ok(details.includes(phrase),phrase);
  assert.match(details,/historical\/stale port association/);
});

test("switch details expose searchable observational interfaces and multiple endpoint truth",()=>{
  for(const phrase of ["Interfaces / ports","Search switch ports","Active ports","Unknown endpoints","Multiple/Unknown endpoint","Interface description"])assert.ok(details.includes(phrase),phrase);
  assert.match(details,/cannot change port configuration/);
  assert.doesNotMatch(details,/enable port|disable port|change VLAN|restart interface/i);
});

test("existing V3A edges and relationship inspector show the port when available",()=>{
  assert.match(topology,/source_port/);
  assert.match(topology,/Switch port/);
  assert.match(topology,/Port status/);
});
