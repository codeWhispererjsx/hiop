export const HIOP_APP_MODE = import.meta.env.VITE_HIOP_APP_MODE ?? "web";
export const isDesktopMode = HIOP_APP_MODE === "desktop";
