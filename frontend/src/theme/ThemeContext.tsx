import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";
export type ThemePreference = Theme | "system";
const STORAGE_KEY = "hiop_theme";
type ThemeContextValue = { theme: Theme; preference: ThemePreference; setPreference: (value: ThemePreference) => void; toggleTheme: () => void };
const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function initialTheme(): Theme {
  const applied = document.documentElement.dataset.theme;
  if (applied === "light" || applied === "dark") return applied;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const saved = localStorage.getItem(STORAGE_KEY);
  const [preference, setPreference] = useState<ThemePreference>(saved === "light" || saved === "dark" || saved === "system" ? saved : "system");
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => setTheme(preference === "system" ? media.matches ? "dark" : "light" : preference);
    apply(); media.addEventListener("change", apply); localStorage.setItem(STORAGE_KEY, preference);
    return () => media.removeEventListener("change", apply);
  }, [preference]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#07110f" : "#f5f3eb");
  }, [theme]);
  const value = useMemo(() => ({ theme, preference, setPreference, toggleTheme: () => setPreference(theme === "dark" ? "light" : "dark") }), [theme, preference]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

// The provider and its hook intentionally share this small module.
// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
