const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("hiopDesktop", {
  mode: "desktop",
  platform: process.platform,
});
