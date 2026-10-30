const test = require("node:test");
const assert = require("node:assert/strict");
const { validateSiteServerUrl } = require("../src/site-server-url.cjs");

test("Site Server URLs are normalized to an origin", () => {
  assert.equal(validateSiteServerUrl("https://hiop.hotel.example/"), "https://hiop.hotel.example");
  assert.equal(validateSiteServerUrl("http://localhost:8765"), "http://localhost:8765");
  assert.equal(validateSiteServerUrl(null), null);
});

test("remote Site Server URLs require HTTPS and reject embedded credentials or paths", () => {
  for (const value of [
    "http://hiop.hotel.example",
    "https://user:password@hiop.hotel.example",
    "https://hiop.hotel.example/api",
    "https://hiop.hotel.example/?token=secret",
    "file:///C:/database",
  ]) {
    assert.throws(() => validateSiteServerUrl(value));
  }
});
