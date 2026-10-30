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

test("desktop launch checks are bounded and provide recovery actions", () => {
  const launch = source("../src/pages/DesktopLaunchPage.tsx");
  const api = source("../src/lib/publicApi.ts");
  assert.match(api, /setTimeout\(\(\)=>controller\.abort\(\),8000\)/);
  assert.match(launch, /attempts >= 3/);
  assert.match(launch, /Retry connection/);
  assert.match(launch, /Continue to/);
  assert.match(launch, /Connect to an existing Site Server/);
});

test("desktop site-server connection provides context-aware back navigation", () => {
  const page = source("../src/pages/DesktopConnectPage.tsx");
  const login = source("../src/pages/LoginPage.tsx");
  const launch = source("../src/pages/DesktopLaunchPage.tsx");
  assert.match(page, /desktop-connect-back/);
  assert.match(page, /returnTo === "\/login" \? "\/login" : "\/desktop-launch"/);
  assert.match(login, /state=\{\{ returnTo: "\/login" \}\}/);
  assert.match(launch, /state=\{\{ returnTo: "\/desktop-launch" \}\}/);
});
