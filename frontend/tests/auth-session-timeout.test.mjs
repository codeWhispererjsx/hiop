import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../src/layouts/DashboardLayout.tsx", import.meta.url),
  "utf8",
);

test("authenticated dashboard logs out after 30 minutes without user activity", () => {
  assert.match(source, /const idleTimeoutMs = 30 \* 60 \* 1000/);
  for (const event of ["pointerdown", "pointermove", "keydown", "touchstart", "wheel"]) {
    assert.match(source, new RegExp(`"${event}"`));
  }
  assert.match(source, /document\.addEventListener\("visibilitychange", checkDeadline\)/);
  assert.match(source, /void logout\(\)/);
  assert.match(source, /await clearAuthToken\(\)/);
  assert.match(source, /navigate\("\/login"\)/);
});
