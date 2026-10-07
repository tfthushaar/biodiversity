import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LayerResult, ZoneReportRow } from "../api/types";

// The real map needs a browser canvas; what matters here is which zone the page asks it to show.
vi.mock("../components/MapView", () => ({
  MapView: ({ selected }: { selected: string | null }) => <div data-testid="map">zone:{selected ?? "all"}</div>,
}));

import { Impact } from "./Impact";
import { MapPage } from "./MapPage";
import { Sources } from "./Sources";
import { buildEntries } from "./SpeciesPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** Answer each REST path from a table; anything unlisted is a 404 so a stray request fails loudly. */
function serve(routes: Record<string, unknown | (() => Response)>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [prefix, body] of Object.entries(routes)) {
      if (url.includes(prefix)) return typeof body === "function" ? (body as () => Response)() : json(body);
    }
    return json({ message: `no route for ${url}` }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const wrap = (ui: ReactElement) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>,
  );

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

const layer = (status: LayerResult["status"], detail: Record<string, unknown>, reason: string | null = null): LayerResult => ({
  layer: "x", status, reason, needs: reason ? "at least 30 invasive records" : null, caution: null, detail,
});

const report = (name: string, slug: string, over: Partial<ZoneReportRow["report"]["layers"]> = {}): ZoneReportRow => ({
  computed_at: new Date().toISOString(),
  zones: { slug, name },
  report: {
    zone: slug,
    observations: 439,
    species: 234,
    invasive_species: [{ species: "Lantana camara", common_name: "common lantana", records: 1, first_record: "2020-01-01", last_record: "2020-01-01", sources: 1 }],
    layers: {
      documented: { status: "ok", findings: [], note: "Only what cited sources report." },
      cooccurrence: layer("insufficient", { cells_usable: 10, required_cells: 20, cells_with_invasives: 3, required_invasive_cells: 5 }, "only 10 usable grid cells (need 20)"),
      trend: layer("insufficient", { usable_years: 9, required_years: 6, invasive_records: 8, required_invasive_records: 30 }, "only 8 invasive records in the zone (need 30)"),
      ...over,
    },
  },
});

describe("Impact page", () => {
  it("refuses to show a statistic when there is too little data, and shows how far off it is", async () => {
    serve({ "/zone_reports": [report("Bandipur National Park", "bandipur")] });
    wrap(<Impact />);
    expect(await screen.findAllByText(/Not enough data to say anything yet/)).toHaveLength(2);
    expect(screen.queryByText(/ρ =/)).not.toBeInTheDocument();
    const meters = screen.getAllByRole("meter");
    expect(meters.map((m) => m.getAttribute("aria-label"))).toEqual([
      "Grid cells with enough native records",
      "…of which also hold invasive records",
      "Years with enough observations",
      "Invasive records in the zone",
    ]);
    expect(screen.getByText(/6 needed, met/)).toBeInTheDocument(); // 9 years against 6 needed
    expect(screen.getByText(/of 30 records/)).toBeInTheDocument();
  });

  it("explains an empty analysis instead of showing nothing", async () => {
    serve({ "/zone_reports": [] });
    wrap(<Impact />);
    expect(await screen.findByText(/No analysis has been computed yet/)).toBeInTheDocument();
  });

  it("starts on the zone with the most invasive species and lets you change it", async () => {
    const quiet = report("Serengeti National Park", "serengeti");
    quiet.report.invasive_species = [];
    serve({ "/zone_reports": [quiet, report("Bandipur National Park", "bandipur")] });
    wrap(<Impact />);
    const select = await screen.findByRole<HTMLSelectElement>("combobox", { name: /zone/i });
    await waitFor(() => expect(select.value).toBe("bandipur"));
    await userEvent.selectOptions(select, "serengeti");
    expect(await screen.findByText(/no invasive species recorded/)).toBeInTheDocument();
  });

  it("says so when the data service fails, and can try again", async () => {
    let calls = 0;
    serve({
      "/zone_reports": () => (++calls === 1 ? json({ message: "down" }, 503) : json([report("Bandipur National Park", "bandipur")])),
    });
    wrap(<Impact />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("503");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByText(/Not enough data/)).not.toHaveLength(0);
  });

  it("shows the correlation only once the data supports it", async () => {
    serve({
      "/zone_reports": [
        report("Bandipur National Park", "bandipur", {
          cooccurrence: layer("ok", { cells_usable: 40, spearman_rho: -0.31, ci95: [-0.52, -0.08] }),
        }),
      ],
    });
    wrap(<Impact />);
    expect(await screen.findByText(/ρ = -0.31/)).toBeInTheDocument();
    expect(screen.getByText(/-0.52 to -0.08/)).toBeInTheDocument();
  });
});

describe("Map page", () => {
  const zones = {
    type: "FeatureCollection",
    features: ["bandipur", "serengeti", "mudumalai"].map((slug, i) => ({
      type: "Feature",
      geometry: null,
      properties: { slug, name: slug, invasive_records: [8, 0, 3][i] },
    })),
  };
  const none = { type: "FeatureCollection", features: [] };

  it("opens on the zone with the most invasive records, not on two continents of specks", async () => {
    serve({ "/rpc/zones_geojson": zones, "/rpc/records_geojson": none });
    wrap(<MapPage />);
    expect(await screen.findByTestId("map")).toHaveTextContent("zone:bandipur");
  });

  it("keeps 'All zones' one choice away, and respects it once chosen", async () => {
    const fetchMock = serve({ "/rpc/zones_geojson": zones, "/rpc/records_geojson": none });
    wrap(<MapPage />);
    const select = await screen.findByRole<HTMLSelectElement>("combobox");
    await waitFor(() => expect(select.value).toBe("bandipur"));
    await userEvent.selectOptions(select, "");
    await waitFor(() => expect(screen.getByTestId("map")).toHaveTextContent("zone:all"));
    expect(select.value).toBe("");
    // The query for all zones carries no zone filter.
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("records_geojson") && !String(u).includes("p_zone"))).toBe(true);
  });

  it("says plainly when a zone has no invasive records", async () => {
    serve({ "/rpc/zones_geojson": zones, "/rpc/records_geojson": none });
    wrap(<MapPage />);
    expect(await screen.findByText(/No invasive-species records in this zone/)).toBeInTheDocument();
  });
});

describe("Sources page", () => {
  const base = { base_url: "https://example.org", attribution: null, license: "CC BY 4.0", last_run: null, fetched: null, skipped_dupe: null, rejected: null };

  it("does not show a checklist as having zero records, and refuses unsafe links", async () => {
    serve({
      "/source_health": [
        { ...base, id: 1, name: "GRIIS", kind: "dataset", items: 0 },
        { ...base, id: 2, name: "Hostile", kind: "api", items: 5, base_url: "javascript:alert(1)", fetched: 10, skipped_dupe: 1 },
      ],
    });
    wrap(<Sources />);
    expect(await screen.findByText("checklist")).toBeInTheDocument();
    expect(screen.getByText("fetched 10, 1 duplicate")).toBeInTheDocument(); // singular, not "1 duplicates"
    expect(screen.getByRole("link", { name: "GRIIS" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Hostile" })).not.toBeInTheDocument(); // shown as text only
    expect(screen.getByText("Hostile")).toBeInTheDocument();
  });
});

describe("species list", () => {
  const sp = (name: string, common: string | null = null) => ({ species: { scientific_name: name, common_name: common } });

  it("puts species with cited evidence first, then the most recorded, then alphabetical", () => {
    const entries = buildEntries(
      [sp("Zzz one"), sp("Aaa two"), sp("Mmm recorded"), sp("Senna spectabilis", "Senna")] as never,
      [{ id: 1, ...sp("Senna spectabilis") }] as never,
      [{ id: 1, ...sp("Senna spectabilis") }, { id: 2, ...sp("Senna spectabilis") }] as never,
      [{ report: { invasive_species: [{ species: "Mmm recorded", records: 4 }] } }] as never,
    );
    expect(entries.map((e) => e.name)).toEqual(["Senna spectabilis", "Mmm recorded", "Aaa two", "Zzz one"]);
    expect(entries[0]).toMatchObject({ findings: 2, playbooks: 1 });
  });

  it("includes a species that has guidance even if the checklist does not list it", () => {
    const entries = buildEntries([], [{ id: 1, ...sp("Only here") }] as never, [], []);
    expect(entries.map((e) => e.name)).toEqual(["Only here"]);
  });
});
