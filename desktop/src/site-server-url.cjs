function validateSiteServerUrl(value) {
  if (value === null || value === "") return null;
  if (typeof value !== "string" || value.length > 2048) {
    throw new Error("Enter a valid HTTPS address for the HIOP Site Server.");
  }
  let server;
  try {
    server = new URL(value.trim());
  } catch {
    throw new Error("Enter a valid HTTPS address for the HIOP Site Server.");
  }
  const isLocalHttp = server.protocol === "http:" && ["localhost", "127.0.0.1"].includes(server.hostname);
  if (server.protocol !== "https:" && !isLocalHttp) {
    throw new Error("Site Server connections must use HTTPS. HTTP is allowed only for localhost testing.");
  }
  if (server.username || server.password || server.search || server.hash || !["", "/"].includes(server.pathname)) {
    throw new Error("Enter only the Site Server origin, without credentials, paths, or query parameters.");
  }
  return server.origin;
}

module.exports = { validateSiteServerUrl };
