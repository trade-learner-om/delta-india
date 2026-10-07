import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { ThemeProvider } from "./utils/theme/ThemeContext";
import { applyThemeClass, readStoredTheme } from "./utils/theme/themeStorage";

applyThemeClass(readStoredTheme());

ReactDOM.createRoot(document.getElementById("root")).render(
  <ThemeProvider>
    <App />
  </ThemeProvider>,
);
