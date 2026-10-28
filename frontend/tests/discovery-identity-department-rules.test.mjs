import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync(new URL("../src/pages/DiscoveryIntelligencePage.tsx", import.meta.url), "utf8");
const deviceForm = fs.readFileSync(new URL("../src/components/DeviceForm.tsx", import.meta.url), "utf8");

test("hostname rules can assign a scoped department independently of device type", () => {
  assert.match(page, /Assign department/);
  assert.match(page, /output_department_id: form\.output_department_id \|\| null/);
  assert.match(page, /Keep detected device type/);
  assert.match(page, /Department: \$\{rule\.department_name\}/);
});

test("identity rule preview shows department suggestions", () => {
  assert.match(page, /Suggested department:/);
});

test("identity rule changes refresh inventory and department pickers", () => {
  assert.equal((page.match(/dispatchEvent\(new Event\("hiop:organization-updated"\)\)/g) ?? []).length, 2);
  assert.match(deviceForm, /useRequest\(endpoints\.hierarchy, \[\]\)/);
});
