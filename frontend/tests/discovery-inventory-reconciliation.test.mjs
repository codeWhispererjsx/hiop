import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../src/pages/DiscoveryIntelligencePage.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("discovery offers reviewed links to exact uploaded inventory matches", () => {
  assert.match(page, /inventory_match_candidates/);
  assert.match(page, /Link \$\{candidate\.asset_number\}/);
  assert.match(page, /Review and link the matching uploaded asset/);
  assert.match(api, /managed_asset_id:managedAssetId/);
});
