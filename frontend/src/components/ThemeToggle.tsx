import { Icon } from "./Icon";
import { useTheme } from "../theme/ThemeContext";

export default function ThemeToggle({ className = "", showLabel = false }: { className?: string; showLabel?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = theme === "dark" ? "light" : "dark";
  return <button className={`icon-button theme-toggle ${showLabel ? "theme-toggle-labelled" : ""} ${className}`.trim()} type="button" onClick={toggleTheme} aria-label={`Switch to ${nextTheme} mode`} title={`Switch to ${nextTheme} mode`} aria-pressed={theme === "dark"}><Icon name={theme === "dark" ? "sun" : "moon"}/>{showLabel&&<span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>}</button>;
}
