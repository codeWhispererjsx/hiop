import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("device and asset pages do not expose endpoint-control actions", () => {
  const details = read("../src/pages/DeviceDetailsPage.tsx");
  const assetDetails = read("../src/pages/AssetDetailsPage.tsx");
  const api = read("../src/lib/api.ts");

  assert.doesNotMatch(details, /createDeviceAgentAction|createManagedAssetAgentAction|Restart device|Shut down device|Lock user session/);
  assert.doesNotMatch(assetDetails, /ManagedAssetActions|createManagedAssetAgentAction/);
  assert.doesNotMatch(api, /createDeviceAgentAction|createManagedAssetAgentAction|wakeDevice/);
});
