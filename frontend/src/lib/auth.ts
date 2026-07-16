const TOKEN_KEY = "hiop_token";

export function getAuthToken(): string | null {
  const current = sessionStorage.getItem(TOKEN_KEY);
  if (current) return current;
  const legacy = localStorage.getItem(TOKEN_KEY);
  if (legacy) {
    sessionStorage.setItem(TOKEN_KEY, legacy);
    localStorage.removeItem(TOKEN_KEY);
  }
  return legacy;
}

export function setAuthToken(token: string): void {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

export function hasUsableToken(): boolean {
  const token = getAuthToken();
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number; iss?: string };
    if (typeof payload.exp !== "number" || payload.exp * 1000 <= Date.now()) {
      clearAuthToken();
      return false;
    }
    if (payload.iss !== "hiop") {
      clearAuthToken();
      return false;
    }
    return true;
  } catch {
    clearAuthToken();
    return false;
  }
}
