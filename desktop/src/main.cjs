const { app, BrowserWindow, shell } = require("electron");
const path = require("path");

const isDev = Boolean(process.env.HIOP_DESKTOP_URL);
const frontendUrl = process.env.HIOP_DESKTOP_URL || `file://${path.join(__dirname, "..", "..", "frontend", "dist", "index.html")}`;

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

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
