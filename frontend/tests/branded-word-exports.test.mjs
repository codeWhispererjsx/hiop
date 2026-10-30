import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const brandedExport = source("../src/lib/brandedWordExport.ts");

test("Word reports use HIOP and organization branding with an actual DOCX packer", () => {
  assert.match(brandedExport, /new docx\.Document\(/);
  assert.match(brandedExport, /docx\.Packer\.toBlob\(document\)/);
  assert.match(brandedExport, /organization\.name/);
  assert.match(brandedExport, /organization\.logo/);
  assert.match(brandedExport, /hospitality-it-ops-wordmark-dark-transparent\.png/);
  assert.match(brandedExport, /\.docx/);
});

test("visible CSV exports offer a branded Word alternative", () => {
  for (const path of [
    "../src/pages/DevicesPage.tsx",
    "../src/pages/ReportingPage.tsx",
    "../src/pages/AdministrationPage.tsx",
    "../src/pages/SystemMaintenancePage.tsx",
    "../src/components/imports/ImportSteps.tsx",
  ]) {
    assert.match(source(path), /download(?:CsvAsBrandedWordReport|BrandedWordReport|ExportFile)/);
    assert.match(source(path), /Word(?: report)?(?: \(\.docx\)| \(\.docx\))?|value="word"/);
  }
});

test("the asset inventory Word report uses readable grouped columns and includes assigned owners", () => {
  const devices = source("../src/pages/DevicesPage.tsx");
  assert.match(devices, /"Asset", "Device", "Assignment", "Technical details", "Network", "Health & lifecycle"/);
  assert.match(devices, /Assigned to: \$\{value\(row\.business_owner\)\}/);
  assert.match(brandedExport, /split\(\/\\r\?\\n\/\)/);
});
