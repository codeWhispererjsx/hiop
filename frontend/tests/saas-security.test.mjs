import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const access = readFileSync(new URL("../src/pages/AccountAccessPage.tsx", import.meta.url), "utf8");
const users = readFileSync(new URL("../src/pages/UsersPage.tsx", import.meta.url), "utf8");
const platform = readFileSync(new URL("../src/pages/PlatformControlCenterPage.tsx", import.meta.url), "utf8");

test("public account lifecycle routes are available without exposing tokens", () => {
  for (const route of ["forgot-password", "reset-password", "verify-email", "accept-invitation"])
    assert.match(app, new RegExp(`path=\"/${route}`));
  assert.match(access, /single-use|secure HIOP account/i);
  assert.doesNotMatch(access, /test_token|token_hash/);
});

test("organization invitations and platform access evidence use secured APIs", () => {
  assert.match(api, /\/accounts\/invitations/);
  assert.match(users, /Invite organization user/);
  assert.match(api, /\/saas-admin\/security\/access-events/);
  assert.match(platform, /Data access events/);
});
