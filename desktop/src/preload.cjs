const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hiopDesktop", {
  mode: "desktop",
  platform: process.platform,
  getSessionToken: () => ipcRenderer.invoke("hiop:session:get"),
  setSessionToken: (token) => ipcRenderer.invoke("hiop:session:set", token),
  clearSessionToken: () => ipcRenderer.invoke("hiop:session:clear"),
  runDeviceAction: (action, target) => ipcRenderer.invoke("hiop:device-action", action, target),
});
