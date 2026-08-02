import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/DashboardPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles/dashboard.css", import.meta.url), "utf8");

test("home is a simple real-data asset workspace", () => {
  for (const text of ["Total assets", "Online now", "Types of assets", "Assets by location", "Asset inventory", "Discover devices"]) {
    assert.match(page, new RegExp(text));
  }
  assert.match(page, /endpoints\.dashboard/);
  assert.match(page, /endpoints\.devices/);
  assert.doesNotMatch(page, /57,842|1,203|dummy|mock/i);
});

test("asset dashboard has responsive empty and populated states", () => {
  assert.match(page, /Discover your first device/);
  assert.match(page, /function AssetTable/);
  assert.match(css, /asset-summary-grid/);
  assert.match(css, /@media\(max-width:650px\)/);
});
