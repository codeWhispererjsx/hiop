import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";

import App from "./App";
import { isDesktopMode } from "./lib/appMode";
import { initializeAuth } from "./lib/auth";
import { ThemeProvider } from "./theme/ThemeContext";
import "./theme/tokens.css";
import "./index.css";
import "./styles/design-system.css";

const Router = isDesktopMode ? HashRouter : BrowserRouter;

const root = createRoot(document.getElementById("root")!);
void initializeAuth().then(() => {
  root.render(
    <StrictMode>
      <Router>
        <ThemeProvider><App /></ThemeProvider>
      </Router>
    </StrictMode>
  );
}).catch((error: unknown) => {
  console.error("Unable to restore the secure HIOP desktop session.", error);
  const message = error instanceof Error ? error.message : "Unable to restore the secure desktop session.";
  document.getElementById("root")!.textContent = `${message} Restart HIOP and sign in again.`;
});
