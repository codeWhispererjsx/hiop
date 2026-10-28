import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("simple inventory import stages only unmatched hosts and explains preserved records", () => {
  const api = read("../src/lib/api.ts");
  const matching = read("../../backend/app/services/import_matching_service.py");
  const finalize = read("../src/components/imports/ImportSteps.tsx");

  assert.match(api, /simple \? "\?simple=true" : ""/);
  assert.match(matching, /candidate\.candidate_device_id/);
  assert.match(matching, /func\.lower\(ManagedAsset\.name\)/);
  assert.match(matching, /"skip", \[\], \[\], actor/);
  assert.match(finalize, /Existing managed asset — unchanged/);
  assert.match(finalize, /Only unmatched hosts are added/);
});
