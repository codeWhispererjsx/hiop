const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const isDev = Boolean(process.env.HIOP_DESKTOP_URL);
const resourcesRoot = process.resourcesPath || path.join(__dirname, "..", "..");
const repoRoot = path.join(__dirname, "..", "..");
const packagedFrontend = path.join(resourcesRoot, "frontend", "index.html");
const devFrontend = path.join(repoRoot, "frontend", "dist", "index.html");
const frontendUrl = process.env.HIOP_DESKTOP_URL || `file://${fs.existsSync(packagedFrontend) ? packagedFrontend : devFrontend}`;
let backendProcess;

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

  backendProcess = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", runtimeScriptPath()], {
    cwd: runtimeWorkingDirectory(),
    env: {
      ...process.env,
      HIOP_DESKTOP_PORT: process.env.HIOP_DESKTOP_PORT || "8765",
      HIOP_DESKTOP_RESOURCES: resourcesRoot,
    },
    windowsHide: true,
    stdio: isDev ? "inherit" : "ignore",
  });

  backendProcess.on("exit", (code) => {
    backendProcess = undefined;
    if (code && code !== 0) {
      dialog.showErrorBox(
        "HIOP backend did not start",
        "The local HIOP service stopped before the desktop app could connect. Check %LOCALAPPDATA%\\HIOP Desktop\\logs\\backend.log."
      );
    }
  });
}

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

  void win.loadURL(frontendUrl);
  if (isDev) win.webContents.openDevTools({ mode: "detach" });
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
});

app.on("before-quit", () => {
  if (backendProcess && !backendProcess.killed) backendProcess.kill();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
