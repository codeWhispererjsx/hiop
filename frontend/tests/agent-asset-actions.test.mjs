import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("device action menu refreshes online agent status and supports managed-asset agents", () => {
  const details = read("../src/pages/DeviceDetailsPage.tsx");
  const assetDetails = read("../src/pages/AssetDetailsPage.tsx");
  const api = read("../src/lib/api.ts");

  assert.match(details, /setInterval\(\(\) => void reloadAgents\(\), 10_000\)/);
  assert.match(details, /agent\?\.status === "online"/);
  assert.match(details, /createManagedAssetAgentAction\(agent\.managed_asset_id, action\)/);
  assert.match(assetDetails, /agent\.managed_asset_id===id/);
  assert.match(assetDetails, /createManagedAssetAgentAction\(asset\.id,confirming\)/);
  assert.match(api, /\/local-agents\/assets\/\$\{assetId\}\/actions/);
});
