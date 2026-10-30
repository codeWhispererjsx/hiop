import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("desktop clients route API and dashboard WebSocket traffic to their Site Server", () => {
  const endpoints = source("../src/lib/desktopServer.ts");
  const api = source("../src/lib/api.ts");
  const websocket = source("../src/layouts/DashboardLayout.tsx");
  assert.match(endpoints, /hiopDesktop\?\.siteServerUrl/);
  assert.match(endpoints, /\/api\/v1/);
  assert.match(endpoints, /wss:/);
  assert.match(api, /getApiBaseUrl\(\)/);
  assert.match(websocket, /getDashboardWebSocketUrl\(\)/);
});

test("desktop connection setup clears prior login context and requires server HTTPS", () => {
  const page = source("../src/pages/DesktopConnectPage.tsx");
  const app = source("../src/App.tsx");
  const main = source("../../desktop/src/main.cjs");
  assert.match(app, /desktop-connect/);
  assert.match(page, /clearAuthToken\(\)/);
  assert.match(page, /serverUrl\.protocol !== "https:"/);
  assert.match(main, /if \(!readSiteServerUrl\(\)\) startBackend\(\)/);
  assert.match(main, /protocol\.registerSchemesAsPrivileged/);
});
