const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const isDev = Boolean(process.env.HIOP_DESKTOP_URL);
const frontendUrl = process.env.HIOP_DESKTOP_URL || `file://${path.join(__dirname, "..", "..", "frontend", "dist", "index.html")}`;
let backendProcess;

function startBackend() {
  if (process.env.HIOP_DESKTOP_NO_BACKEND === "1") return;

  const repoRoot = path.join(__dirname, "..", "..");
  const script = path.join(repoRoot, "desktop", "runtime", "start-local-backend.ps1");
  backendProcess = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script], {
    cwd: repoRoot,
    env: {
      ...process.env,
      HIOP_DESKTOP_PORT: process.env.HIOP_DESKTOP_PORT || "8765",
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

