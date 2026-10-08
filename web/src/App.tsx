import { useEffect, useState, type ReactElement } from "react";
import { Icon } from "./components/icons";
import { Alerts } from "./pages/Alerts";
import { Impact } from "./pages/Impact";
import { Hotspots } from "./pages/Hotspots";
import { Models } from "./pages/Models";
import { Overview } from "./pages/Overview";
import { Sources } from "./pages/Sources";
import { SpeciesPage } from "./pages/SpeciesPage";
import { applyChoice, readChoice, resolve, type ThemeChoice } from "./lib/theme";

const NAV = [
  { path: "/", label: "Overview" },
  { path: "/hotspots", label: "Hotspots" },
  { path: "/species", label: "Species" },
  { path: "/impact", label: "Impact" },
  { path: "/alerts", label: "Alerts" },
  { path: "/models", label: "Models" },
  { path: "/sources", label: "Sources" },
];

function currentPath(): string {
  const h = window.location.hash.replace(/^#/, "");
  return h.startsWith("/") ? h : "/";
}

export function useHashPath(): string {
  const [path, setPath] = useState(currentPath);
  useEffect(() => {
    const on = () => setPath(currentPath());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return path;
}

export function route(path: string): ReactElement {
  const [base, ...rest] = path.split("/").filter(Boolean);
  switch (base) {
    case undefined:
      return <Overview />;
    case "hotspots":
    case "map":
      return <Hotspots zone={rest.length ? decodeURIComponent(rest[0] ?? "") : null} />;
    case "impact":
      return <Impact />;
    case "species":
      return <SpeciesPage selected={rest.length ? decodeURIComponent(rest.join("/")) : null} />;
    case "alerts":
      return <Alerts />;
    case "models":
      return <Models />;
    case "sources":
      return <Sources />;
    default:
      return (
        <div className="card">
          <h1>Page not found</h1>
          <p className="lede">
            There is nothing at <code>{path}</code>. <a href="#/">Back to the overview</a>.
          </p>
        </div>
      );
  }
}

function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(readChoice);
  const next: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
  const label = choice === "system" ? `Theme: automatic (${resolve()})` : `Theme: ${choice}`;
  return (
    <button
      className="btn icon-only"
      aria-label={label}
      title={label}
      onClick={() => {
        setChoice(next[choice]);
        applyChoice(next[choice]);
      }}
    >
      <Icon name={choice === "dark" ? "moon" : choice === "light" ? "sun" : "auto"} />
    </button>
  );
}

export default function App() {
  const path = useHashPath();
  const active = "/" + (path.split("/").filter(Boolean)[0] ?? "");
  // Move focus to the page heading on navigation, so keyboard and screen-reader users land at
  // the top of the new view instead of staying on the link they pressed.
  useEffect(() => {
    document.getElementById("main")?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [active]);

  return (
    <>
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/">Biodiversity Monitor</a>
          <nav aria-label="Main">
            {NAV.map((n) => (
              <a key={n.path} href={`#${n.path}`} aria-current={active === n.path ? "page" : undefined}>
                {n.label}
              </a>
            ))}
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main id="main" tabIndex={-1} style={{ outline: "none" }}>
        {route(path)}
      </main>
      <footer>
        Open data from iNaturalist, GBIF, GRIIS and the U.S. Geological Survey, each under its own
        licence (see Sources). Map data © OpenStreetMap contributors. Code and methods:{" "}
        <a href="https://github.com/tfthushaar/biodiversity" target="_blank" rel="noopener noreferrer">
          github.com/tfthushaar/biodiversity
        </a>
        .
      </footer>
    </>
  );
}
