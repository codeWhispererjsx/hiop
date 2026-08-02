import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");
const luminance = (hex) => {
  const channels = hex.match(/[\da-f]{2}/gi).map((value) => Number.parseInt(value, 16) / 255).map((value) => value <= .03928 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
};
const contrast = (a, b) => {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + .05) / (dark + .05);
};

test("official Enterprise and Hospitality palette is centralized in theme tokens", () => {
  const tokens = read("src/theme/tokens.css").toLowerCase();
  for (const color of ["#2563eb", "#1e3a8a", "#22c55e", "#d4af37", "#f8fafc", "#0f172a", "#e5e7eb", "#111827", "#0b1220", "#020617"]) {
    assert.match(tokens, new RegExp(color));
  }
  for (const scale of ["--space-", "--radius-", "--shadow-", "--z-", "--font-"]) assert.match(tokens, new RegExp(scale));
});

test("gold is the accent and green is reserved for explicit status semantics", () => {
  const tokens = read("src/theme/tokens.css").toLowerCase();
  const shared = read("src/styles/design-system.css");
  const dashboard = read("src/styles/dashboard.css");
  assert.match(tokens, /--color-accent:\s*#d4af37/);
  assert.match(tokens, /--color-success:\s*#22c55e/);
  assert.match(shared, /\.tone-success[\s\S]*var\(--color-success\)/);
  assert.doesNotMatch(dashboard, /\.stat-card\s*\{[^}]*color-success/);
  assert.doesNotMatch(dashboard, /\.panel\s*\{[^}]*color-success/);
  assert.doesNotMatch(dashboard, /\.stat-card\s*\{[^}]*linear-gradient/);
});

test("core text and action pairs meet WCAG AA contrast", () => {
  for (const [foreground, background] of [["111827", "ffffff"], ["6b7280", "ffffff"], ["ffffff", "2563eb"], ["f8fafc", "111827"], ["a8b3c5", "111827"], ["f8fafc", "0f172a"]]) {
    assert.ok(contrast(foreground, background) >= 4.5, `${foreground} on ${background}`);
  }
});

test("literal interface colors exist only in the centralized token file", () => {
  const source = fileURLToPath(new URL("src/", root));
  const paths = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (/\.(css|ts|tsx)$/.test(entry.name) && !path.endsWith("tokens.css")) paths.push(path);
    }
  };
  visit(source);
  for (const path of paths) {
    const contents = readFileSync(path, "utf8");
    assert.doesNotMatch(contents, /#[\da-f]{3,8}|rgba?\(/i, path);
  }
});

test("shared components use semantic surfaces, controls, focus, and responsive rules", () => {
  const styles = read("src/styles/design-system.css");
  for (const selector of [".sidebar", ".topbar", ".stat-card", ".primary-action", ".status-badge", ".modal", ".toast-notification", ":focus"]) {
    assert.match(styles, new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(styles, /@media \(max-width: 820px\)/);
  assert.match(styles, /var\(--color-primary\)/);
});

test("theme switching remains instant, system-aware, and persisted", () => {
  const context = read("src/theme/ThemeContext.tsx");
  const bootstrap = read("public/theme-init.js");
  assert.match(context, /localStorage\.setItem\(STORAGE_KEY, preference\)/);
  assert.match(context, /prefers-color-scheme: dark/);
  assert.match(context, /document\.documentElement\.dataset\.theme = theme/);
  assert.match(bootstrap, /localStorage\.getItem\("hiop_theme"\)/);
});
