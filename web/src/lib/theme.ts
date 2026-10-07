import { useEffect, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";
export type Resolved = "light" | "dark";
const KEY = "biodiv-theme";

export function readChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system"; // storage can be blocked (private windows); the page must still work
  }
}

export function applyChoice(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    /* ignore */
  }
}

export function resolve(): Resolved {
  const stamped = document.documentElement.getAttribute("data-theme");
  if (stamped === "light" || stamped === "dark") return stamped;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** The theme actually in effect, updating when the toggle or the OS setting changes. */
export function useResolvedTheme(): Resolved {
  const [theme, setTheme] = useState<Resolved>(resolve);
  useEffect(() => {
    const update = () => setTheme(resolve());
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    mq?.addEventListener("change", update);
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      mq?.removeEventListener("change", update);
      obs.disconnect();
    };
  }, []);
  return theme;
}

/** Read a design token, for the places (a canvas map) that cannot use CSS variables. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}
