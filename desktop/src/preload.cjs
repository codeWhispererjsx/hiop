const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hiopDesktop", {
  mode: "desktop",
  platform: process.platform,
  runDeviceAction: (action, target) => ipcRenderer.invoke("hiop:device-action", action, target),
});
