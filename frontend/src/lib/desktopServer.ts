const configuredApiUrl = import.meta.env.VITE_API_URL ?? "/api/v1";
const configuredWebSocketUrl = import.meta.env.VITE_WS_URL;

export function getApiBaseUrl(): string {
  const siteServerUrl = window.hiopDesktop?.siteServerUrl;
  return siteServerUrl ? `${siteServerUrl}/api/v1` : configuredApiUrl;
}

export function getDashboardWebSocketUrl(): string {
  const siteServerUrl = window.hiopDesktop?.siteServerUrl;
  if (siteServerUrl) {
    const server = new URL(siteServerUrl);
    const protocol = server.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${server.host}/ws/dashboard`;
  }
  if (configuredWebSocketUrl?.startsWith("http")) {
    return `${configuredWebSocketUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:").replace(/\/api\/v1\/?$/, "")}/ws/dashboard`;
  }
  if (configuredWebSocketUrl?.startsWith("/")) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${configuredWebSocketUrl}`;
  }
  return configuredWebSocketUrl ??
    `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
}
