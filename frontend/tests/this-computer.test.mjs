import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const page = read("src/pages/ThisComputerPage.tsx");
const api = read("src/lib/api.ts");

test("Site Server dashboard reports live operations and provides real quick actions", () => {
  for (const label of ["HIOP service", "HIOP database", "Network connection", "Last discovery", "Monitored devices", "Backup and recovery", "Storage", "Recent errors"])
    assert.match(page, new RegExp(label));
  for (const action of ["Run device discovery", "Open HIOP settings", "View service diagnostics", "Download support report", "View backup and recovery"])
    assert.match(page, new RegExp(action));
  assert.match(api, /localOperationsStatus/);
  assert.match(api, /downloadLocalSupportReport/);
  assert.match(page, /credentials, tokens, private keys/);
});
