// Pages an administrator can choose as the organization's default landing page.
export const LANDING_PAGES = [
  { value: "/dashboard", label: "Overview" },
  { value: "/devices", label: "Manage · assets" },
  { value: "/network", label: "Monitor · network" },
  { value: "/discovery-intelligence", label: "Discover" },
  { value: "/alerts", label: "Alerts & events" },
  { value: "/incidents", label: "Incidents" },
  { value: "/reports", label: "Reports" },
] as const;

// Earlier versions saved routes that no longer exist.
const LEGACY_LANDING_PAGES: Record<string, string> = {
  "/discovery": "/discovery-intelligence",
  "/tickets": "/incidents",
};

export function resolveLandingPage(value: string | null | undefined): string {
  const page = value ? LEGACY_LANDING_PAGES[value] ?? value : "/dashboard";
  return LANDING_PAGES.some((option) => option.value === page) ? page : "/dashboard";
}
