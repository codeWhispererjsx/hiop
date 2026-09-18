import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";

import App from "./App";
import { isDesktopMode } from "./lib/appMode";
import { ThemeProvider } from "./theme/ThemeContext";
import "./theme/tokens.css";
import "./index.css";
import "./styles/design-system.css";

const Router = isDesktopMode ? HashRouter : BrowserRouter;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Router>
      <ThemeProvider><App /></ThemeProvider>
    </Router>
  </StrictMode>
);
