import { isDesktopMode } from "./appMode";

const TOKEN_KEY = "hiop_token";
const ORGANIZATION_KEY = "hiop.organization_context";
const RESTORE_WARNING_KEY = "hiop.auth_restore_warning";

declare global {
  interface Window {
    hiopDesktop?: {
      mode: "desktop";
      platform: string;
      siteServerUrl: string | null;
      saveSiteServerUrl: (url: string | null) => Promise<{ ok: true }>;
      ensureLocalBackend: () => Promise<{ ok: true }>;
      getSessionToken: () => Promise<string | null>;
      setSessionToken: (token: string) => Promise<void>;
      clearSessionToken: () => Promise<void>;
      runDeviceAction: (action: string, target: string) => Promise<{ ok: true }>;
    };
  }
}

function tokenIsUsable(token: string): boolean {
  try {
    const encodedPayload = token.split(".")[1];
    if (!encodedPayload) return false;
    const payload = JSON.parse(atob(encodedPayload.replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number; iss?: string };
    return typeof payload.exp === "number" && payload.exp * 1000 > Date.now() && payload.iss === "hiop";
  } catch {
    return false;
  }
}

export async function initializeAuth(): Promise<void> {
  const desktop = window.hiopDesktop;
  if (!desktop) {
    if (isDesktopMode) throw new Error("HIOP secure desktop storage is unavailable.");
    return;
  }

  let savedToken: string | null;
  try {
    savedToken = await desktop.getSessionToken();
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("could not be decrypted and was removed")) throw error;
    sessionStorage.setItem(RESTORE_WARNING_KEY, error.message);
    savedToken = null;
  }
  const legacyToken = sessionStorage.getItem(TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY);
  const token = savedToken && tokenIsUsable(savedToken) ? savedToken : legacyToken;
  if (token && tokenIsUsable(token)) {
    if (!savedToken) await desktop.setSessionToken(token);
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.removeItem(RESTORE_WARNING_KEY);
    localStorage.removeItem(TOKEN_KEY);
    return;
  }

  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
  if (savedToken) await desktop.clearSessionToken();
}

export function getAuthToken(): string | null {
  const current = sessionStorage.getItem(TOKEN_KEY);
  if (current) return current;
  if (isDesktopMode) return null;
  const legacy = localStorage.getItem(TOKEN_KEY);
  if (legacy) {
    sessionStorage.setItem(TOKEN_KEY, legacy);
    localStorage.removeItem(TOKEN_KEY);
  }
  return legacy;
}

export async function setAuthToken(token: string): Promise<void> {
  if (isDesktopMode) {
    if (!window.hiopDesktop) throw new Error("HIOP secure desktop storage is unavailable.");
    await window.hiopDesktop.setSessionToken(token);
  }
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.removeItem(RESTORE_WARNING_KEY);
}

export async function clearAuthToken(): Promise<void> {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(RESTORE_WARNING_KEY);
  sessionStorage.removeItem(ORGANIZATION_KEY);
  localStorage.removeItem("hiop.active_property_id");
  if (isDesktopMode) {
    if (!window.hiopDesktop) throw new Error("HIOP secure desktop storage is unavailable.");
    try {
      await window.hiopDesktop.clearSessionToken();
    } catch (error) {
      sessionStorage.setItem(RESTORE_WARNING_KEY, "HIOP could not remove the saved sign-in from secure storage. Sign in again only after the storage issue is resolved.");
      window.dispatchEvent(new Event("hiop:auth-storage-error"));
      throw error;
    }
  }
}

export const getOrganizationContext=()=>sessionStorage.getItem(ORGANIZATION_KEY);
export const setOrganizationContext=(id:string|null)=>id?sessionStorage.setItem(ORGANIZATION_KEY,id):sessionStorage.removeItem(ORGANIZATION_KEY);

export function hasUsableToken(): boolean {
  const token = getAuthToken();
  if (!token) return false;
  if (tokenIsUsable(token)) return true;
  void clearAuthToken().catch((error: unknown) => console.error("Unable to clear the expired HIOP session.", error));
  return false;
}
