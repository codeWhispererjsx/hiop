const { app, BrowserWindow, dialog, shell, ipcMain, safeStorage, protocol, net } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { pathToFileURL } = require("url");
const { validateSiteServerUrl } = require("./site-server-url.cjs");

protocol.registerSchemesAsPrivileged([{
  scheme: "hiop",
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
}]);

const isDev = Boolean(process.env.HIOP_DESKTOP_URL);
if (isDev) {
  app.setPath("userData", path.join(app.getPath("appData"), "HIOP Desktop Dev"));
}
const resourcesRoot = process.resourcesPath || path.join(__dirname, "..", "..");
const repoRoot = path.join(__dirname, "..", "..");
const packagedFrontend = path.join(resourcesRoot, "frontend", "index.html");
const devFrontend = path.join(repoRoot, "frontend", "dist", "index.html");
const frontendRoot = path.dirname(fs.existsSync(packagedFrontend) ? packagedFrontend : devFrontend);
const frontendUrl = process.env.HIOP_DESKTOP_URL || "hiop://desktop/index.html";
let backendProcess;
let mainWindow;

function siteServerConfigPath() {
  return path.join(app.getPath("userData"), "site-server.json");
}

function readSiteServerUrl() {
  const configPath = siteServerConfigPath();
  if (!fs.existsSync(configPath)) return null;
  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  return validateSiteServerUrl(config.siteServerUrl);
}

function validNetworkTarget(value) {
  const target = String(value || "").trim();
  return /^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/.test(target) && !target.includes("..");
}

function openCommandWindow(title, command, target) {
  const process = spawn("cmd.exe", ["/c", "start", `\"${title}\"`, "cmd.exe", "/k", `${command} ${target}`], {
    detached: true, stdio: "ignore", windowsHide: false,
  });
  process.unref();
}

function assertTrustedRenderer(event) {
  if (!mainWindow || event.sender !== mainWindow.webContents) {
    throw new Error("Session storage is only available to the HIOP window.");
  }
  const senderUrl = event.senderFrame && event.senderFrame.url;
  let sender;
  let expected;
  try {
    sender = new URL(senderUrl);
    expected = new URL(frontendUrl);
  } catch {
    throw new Error("Session storage is unavailable to this page.");
  }
  if (sender.protocol !== expected.protocol || sender.host !== expected.host ||
      (isDev ? sender.origin !== expected.origin : sender.pathname !== expected.pathname)) {
    throw new Error("Session storage is unavailable to this page.");
  }
}

function sessionTokenPath() {
  return path.join(app.getPath("userData"), "auth-session.bin");
}

function requireEncryptedStorage() {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error("Windows secure storage is unavailable. HIOP cannot save this session safely.");
  }
}

ipcMain.handle("hiop:session:get", (event) => {
  assertTrustedRenderer(event);
  requireEncryptedStorage();
  const tokenPath = sessionTokenPath();
  if (!fs.existsSync(tokenPath)) return null;
  try {
    return safeStorage.decryptString(fs.readFileSync(tokenPath));
  } catch {
    fs.rmSync(tokenPath, { force: true });
    throw new Error("The saved HIOP desktop session could not be decrypted and was removed. Sign in again.");
  }
});

ipcMain.handle("hiop:session:set", (event, token) => {
  assertTrustedRenderer(event);
  requireEncryptedStorage();
  if (typeof token !== "string" || token.length > 8192 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token)) {
    throw new Error("The HIOP session token is invalid.");
  }
  fs.writeFileSync(sessionTokenPath(), safeStorage.encryptString(token), { mode: 0o600 });
});

ipcMain.handle("hiop:session:clear", (event) => {
  assertTrustedRenderer(event);
  fs.rmSync(sessionTokenPath(), { force: true });
});

ipcMain.on("hiop:site-server:get", (event) => {
  assertTrustedRenderer(event);
  event.returnValue = readSiteServerUrl();
});

ipcMain.handle("hiop:site-server:set", (event, value) => {
  assertTrustedRenderer(event);
  const siteServerUrl = validateSiteServerUrl(value);
  const configPath = siteServerConfigPath();
  if (siteServerUrl) {
    const temporaryPath = `${configPath}.tmp`;
    fs.writeFileSync(temporaryPath, JSON.stringify({ siteServerUrl }), { mode: 0o600 });
    fs.renameSync(temporaryPath, configPath);
  } else {
    fs.rmSync(configPath, { force: true });
  }
  fs.rmSync(sessionTokenPath(), { force: true });
  setTimeout(() => {
    app.relaunch();
    app.quit();
  }, 150);
  return { ok: true };
});

ipcMain.handle("hiop:device-action", async (_event, action, rawTarget) => {
  if (!validNetworkTarget(rawTarget)) throw new Error("This device does not have a usable hostname or IP address.");
  const target = String(rawTarget).trim();
  if (action === "ping") openCommandWindow("HIOP Ping", "ping", target);
  else if (action === "trace") openCommandWindow("HIOP Trace Route", "tracert", target);
  else if (action === "ssh") openCommandWindow("HIOP SSH", "ssh", target);
  else if (action === "rdp") { const process = spawn("mstsc.exe", [`/v:${target}`], { detached: true, stdio: "ignore", windowsHide: false }); process.unref(); }
  else if (action === "http" || action === "https") await shell.openExternal(`${action}://${target}`);
  else throw new Error("Unsupported device action.");
  return { ok: true };
});

// HIOP owns one private local API port. A second desktop process must bring
// the existing window forward instead of attempting to launch another API.
const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
}

function runtimeScriptPath() {
  const packagedScript = path.join(resourcesRoot, "runtime", "start-local-backend.ps1");
  if (fs.existsSync(packagedScript)) return packagedScript;
  return path.join(repoRoot, "desktop", "runtime", "start-local-backend.ps1");
}

function runtimeWorkingDirectory() {
  const packagedBackend = path.join(resourcesRoot, "backend");
  if (fs.existsSync(packagedBackend)) return resourcesRoot;
  return repoRoot;
}

function startBackend() {
  if (process.env.HIOP_DESKTOP_NO_BACKEND === "1") return;
  if (backendProcess && backendProcess.exitCode === null) return;

  const child = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", runtimeScriptPath()], {
    cwd: runtimeWorkingDirectory(),
    env: {
      ...process.env,
      HIOP_DESKTOP_PORT: process.env.HIOP_DESKTOP_PORT || "8765",
      HIOP_DESKTOP_RESOURCES: resourcesRoot,
      APP_VERSION: app.getVersion(),
    },
    windowsHide: true,
    stdio: isDev ? "inherit" : "ignore",
  });

  backendProcess = child;
  child.on("error", (error) => {
    if (backendProcess === child) backendProcess = undefined;
    dialog.showErrorBox(
      "HIOP local service could not start",
      `The local HIOP service launcher failed: ${error.message}`
    );
  });
  child.on("exit", (code) => {
    if (backendProcess === child) backendProcess = undefined;
    if (code && code !== 0) {
      dialog.showErrorBox(
        "HIOP local service could not start",
        "HIOP could not start the service on this computer. Your local database was not reset. Retry startup, or check %LOCALAPPDATA%\\HIOP Desktop\\logs\\backend.log for details."
      );
    }
  });
}

ipcMain.handle("hiop:backend:ensure", (event) => {
  assertTrustedRenderer(event);
  if (readSiteServerUrl()) {
    throw new Error("This computer is configured to use a remote Site Server.");
  }
  if (process.env.HIOP_DESKTOP_NO_BACKEND === "1") {
    throw new Error("The local HIOP service is disabled for this desktop session.");
  }
  startBackend();
  return { ok: true };
});

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    title: "HIOP Desktop",
    backgroundColor: "#050b1d",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });

  void win.loadURL(frontendUrl);
  if (isDev) win.webContents.openDevTools({ mode: "detach" });
  mainWindow = win;
  win.on("closed", () => {
    if (mainWindow === win) mainWindow = undefined;
  });
  return win;
}

if (hasSingleInstanceLock) {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    if (!process.env.HIOP_DESKTOP_URL) {
      await protocol.handle("hiop", async (request) => {
        const requestUrl = new URL(request.url);
        if (requestUrl.hostname !== "desktop") return new Response("Not found", { status: 404 });
        const requestedPath = decodeURIComponent(requestUrl.pathname);
        const filePath = path.resolve(frontendRoot, `.${requestedPath}`);
        const relativePath = path.relative(frontendRoot, filePath);
        if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
          return new Response("Not found", { status: 404 });
        }
        try {
          return await net.fetch(pathToFileURL(filePath).toString());
        } catch {
          return new Response("Not found", { status: 404 });
        }
      });
    }
    if (!readSiteServerUrl()) startBackend();
    createWindow();
  }).catch((error) => {
    dialog.showErrorBox("HIOP Desktop could not start", error instanceof Error ? error.message : "The desktop runtime configuration is invalid.");
    app.quit();
  });
}

app.on("before-quit", () => {
  if (backendProcess && !backendProcess.killed) backendProcess.kill();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
