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
  assert.match(launch, /const maxAttempts = siteServerUrl \? 3 : 24/);
  assert.match(launch, /attempts >= maxAttempts/);
  assert.match(launch, /ensureLocalBackend\(\)/);
  assert.match(launch, /Retry local startup/);
  assert.match(launch, /Continue to/);
  assert.match(launch, /siteServerUrl && <Link/);
  assert.doesNotMatch(launch, /Connect to an existing Site Server/);
  assert.match(api, /local HIOP service/);
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

test("desktop backend disables SQL debug echo to prevent runaway logs", () => {
  const runtime = source("../../desktop/runtime/start-local-backend.ps1");
  assert.match(runtime, /\$env:DEBUG = "false"/);
  assert.doesNotMatch(runtime, /\$env:DEBUG = "true"/);
  assert.doesNotMatch(runtime, /Remove-Item\s+-Recurse\s+-Force\s+\$postgresData/);
  assert.match(runtime, /existing local database was preserved/i);
  assert.match(runtime, /Bundled PostgreSQL is already running; waiting for local database recovery/);
  assert.match(runtime, /\$pgCtl "-D" \$postgresData "status"/);
});

test("local startup retry can safely restart the backend but never remote clients", () => {
  const main = source("../../desktop/src/main.cjs");
  const preload = source("../../desktop/src/preload.cjs");
  const auth = source("../src/lib/auth.ts");
  assert.match(main, /ipcMain\.handle\("hiop:backend:ensure"/);
  assert.match(main, /if \(readSiteServerUrl\(\)\)/);
  assert.match(main, /if \(backendProcess && backendProcess\.exitCode === null\) return/);
  assert.match(preload, /ensureLocalBackend: \(\) => ipcRenderer\.invoke\("hiop:backend:ensure"\)/);
  assert.match(auth, /ensureLocalBackend: \(\) => Promise<\{ ok: true \}>/);
});
