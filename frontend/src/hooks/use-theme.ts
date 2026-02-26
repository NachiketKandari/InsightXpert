import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

function getThemeSnapshot(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = localStorage.getItem("theme");
  return stored === "light" ? "light" : "dark";
}

function getServerSnapshot(): Theme {
  return "dark";
}

function subscribeTheme(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getServerSnapshot);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next);

    const applyTheme = () => {
      if (next === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
      // Dispatch inside the transition so useSyncExternalStore picks up the change
      window.dispatchEvent(new StorageEvent("storage", { key: "theme" }));
    };

    if ("startViewTransition" in document) {
      (document as Document & { startViewTransition: (cb: () => void) => void }).startViewTransition(applyTheme);
    } else {
      applyTheme();
    }
  };

  return { theme, toggle };
}
