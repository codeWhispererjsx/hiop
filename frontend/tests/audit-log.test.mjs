import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const page = read("src/pages/AdministrationPage.tsx");
const api = read("src/lib/api.ts");

test("audit history uses scoped filters and exports the current filter set", () => {
  for (const label of ["From", "To", "User", "Action", "Area / module", "Outcome", "Property", "Reset filters"])
    assert.match(page, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(page, /endpoints\.auditLogs\(auditFilters\)/);
  assert.match(page, /endpoints\.exportAuditLogs\(\{\.\.\.auditFilters/);
  assert.match(api, /auditLogs: \(filters/);
  assert.match(api, /exportAuditLogs: \(filters/);
});
