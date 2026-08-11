import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const network=readFileSync(new URL("../src/pages/NetworkPage.tsx",import.meta.url),"utf8");
const device=readFileSync(new URL("../src/pages/DeviceDetailsPage.tsx",import.meta.url),"utf8");
const api=readFileSync(new URL("../src/lib/api.ts",import.meta.url),"utf8");

test("V3D exposes read-only time-window health intelligence",()=>{
  for(const value of ["1h","24h","7d","30d"]) assert.match(network,new RegExp(`value="${value}"`));
  assert.match(api,/monitoring\/summary/);
  assert.match(api,/monitoring\/devices/);
  assert.doesNotMatch(api,/monitoring.*delete|monitoring.*put/i);
});

test("device details explain unknown and supported health evidence",()=>{
  for(const label of ["Current health","Availability (24h)","Packet loss","Hardware / system telemetry","Not enough historical data yet"]) assert.ok(device.includes(label));
});
