import { Icon } from "./Icon";
import { useTheme } from "../theme/ThemeContext";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = theme === "dark" ? "light" : "dark";
  return <button className={`icon-button theme-toggle ${className}`.trim()} type="button" onClick={toggleTheme} aria-label={`Switch to ${nextTheme} mode`} title={`Switch to ${nextTheme} mode`} aria-pressed={theme === "dark"}><Icon name={theme === "dark" ? "sun" : "moon"}/></button>;
}
