import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LayerResult, ZoneReportRow } from "../api/types";

// The real map needs a browser canvas. This stand-in offers each square as a button, which is all
// the page needs from it: which squares it was given, and a way to choose one.
vi.mock("../components/HotspotMap", () => ({
  HotspotMap: ({
    cells,
    onSelect,
  }: {
    cells: { west: number; south: number; records: number }[];
    onSelect: (key: string) => void;
  }) => (
    <div data-testid="map">
      {cells.map((c) => (
        <button key={`${c.west}${c.south}`} onClick={() => onSelect(`${c.west.toFixed(4)},${c.south.toFixed(4)}`)}>
          square of {c.records}
        </button>
      ))}
    </div>
  ),
}));

import { Impact } from "./Impact";
import { Alerts } from "./Alerts";
import { Hotspots } from "./Hotspots";
import { Overview } from "./Overview";
import { Sources } from "./Sources";
import { SpeciesPage, buildEntries } from "./SpeciesPage";

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

describe("Hotspots page", () => {
  const square = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]];
  const zones = {
    type: "FeatureCollection",
    features: [
      ["bandipur", "Bandipur National Park", "IN", 8],
      ["serengeti", "Serengeti National Park", "TZ", 0],
      ["everglades", "Everglades National Park", "US", 90],
    ].map(([slug, name, country, n]) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: square },
      properties: { slug, name, country, group: null, observations: 100, species: 10, invasive_records: n, invasive_species: 1 },
    })),
  };
  const sp = (name: string, common: string | null, records: number, first = 2015, last = 2024) => ({
    name, common_name: common, records, first_year: first, last_year: last,
  });
  const cell = (west: number, species: ReturnType<typeof sp>[]) => ({
    west, south: 25, east: west + 0.05, north: 25.05,
    records: species.reduce((a, x) => a + x.records, 0), species_count: species.length, species,
  });
  const hotspots = {
    cell: 0.05,
    cells: [
      cell(-80.6, [sp("Python bivittatus", "Burmese python", 40), sp("Pterois volitans", "Red lionfish", 5)]),
      cell(-80.5, [sp("Pterois volitans", "Red lionfish", 12)]),
    ],
  };
  const finding = {
    id: 1, finding_type: "impact", affected: "marsh rabbits and raccoons", certainty: "observational",
    summary: "Mammal numbers fell sharply where pythons were established.",
    region_note: "Everglades National Park, Florida", source_quotes: ["Severe mammal declines coincide"],
    citation_text: "Dorcas et al. 2012", citation_url: "https://doi.org/10.1073/pnas.1115226109", verified_on: "2026-10-08",
    species: { scientific_name: "Python bivittatus", common_name: "Burmese python" }, zones: null,
  };
  const photo = (over = {}) => ({
    scientific_name: "Python bivittatus", common_name: "Burmese python",
    photo_url: "https://static.example.org/python.jpg", photo_credit: "(c) Wayne Fidler, some rights reserved (CC BY-NC)",
    photo_license: "cc-by-nc", photo_source_url: "https://www.inaturalist.org/photos/1", ...over,
  });
  const routes = (over: Record<string, unknown> = {}) => ({
    "/rpc/zones_geojson": zones,
    "/rpc/hotspot_cells": hotspots,
    "/impact_findings": [finding],
    "/mitigation_playbooks": [],
    "/species?select": [photo()],
    ...over,
  });

  it("opens on the park with the most invasive records and asks for that park's squares", async () => {
    const fetchMock = serve(routes());
    wrap(<Hotspots zone={null} />);
    expect(await screen.findByTestId("map")).toBeInTheDocument();
    const asked = fetchMock.mock.calls.map(([u]) => String(u)).find((u) => u.includes("hotspot_cells"))!;
    expect(asked).toContain("p_zone=everglades");
    const select = screen.getByRole<HTMLSelectElement>("combobox", { name: "Park" });
    expect(select.value).toBe("everglades");
  });

  it("opens the park named in the address", async () => {
    const fetchMock = serve(routes());
    wrap(<Hotspots zone="bandipur" />);
    await screen.findByTestId("map");
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("p_zone=bandipur"))).toBe(true);
  });

  it("groups parks by country", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await screen.findByTestId("map");
    const groups = [...document.querySelectorAll("optgroup")].map((g) => g.label);
    expect(groups).toEqual(["India", "Tanzania", "United States"]);
  });

  it("ranks the busiest squares and the most recorded species", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    const buttons = await screen.findAllByRole("button", { name: /records?\b/ });
    expect(buttons[0]).toHaveTextContent("45 records");
    expect(buttons[0]).toHaveTextContent("Burmese python");
    expect(screen.getByRole("list", { name: "Most recorded invasive species in this park" })).toBeInTheDocument();
  });

  it("shows a species card with photo, credit, record count and cited effects when a square is chosen", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await userEvent.click(await screen.findByRole("button", { name: "square of 45" }));
    const card = await screen.findByRole("article", { name: "Burmese python" });
    expect(within(card).getByRole("img", { name: "Photograph of Burmese python" })).toHaveAttribute("src", "https://static.example.org/python.jpg");
    expect(within(card).getByText(/Wayne Fidler/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Photo page" })).toHaveAttribute("href", "https://www.inaturalist.org/photos/1");
    expect(within(card).getByText("40 records here")).toBeInTheDocument();
    expect(within(card).getByText("2015 to 2024")).toBeInTheDocument();
    expect(within(card).getByText(/Mammal numbers fell sharply/)).toBeInTheDocument();
    expect(within(card).getByText(/Everglades National Park, Florida/)).toBeInTheDocument();
  });

  it("says plainly when a species has no photo or no cited research", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await userEvent.click(await screen.findByRole("button", { name: "square of 45" }));
    const lionfish = await screen.findByRole("article", { name: "Red lionfish" });
    expect(within(lionfish).getByText("No openly licensed photo available")).toBeInTheDocument();
    expect(within(lionfish).queryByRole("img")).not.toBeInTheDocument();
    expect(within(lionfish).getByText(/No cited research on this species/)).toBeInTheDocument();
  });

  it("never renders an image address that could run code", async () => {
    serve(routes({ "/species?select": [photo({ photo_url: "javascript:alert(1)" })] }));
    wrap(<Hotspots zone={null} />);
    await userEvent.click(await screen.findByRole("button", { name: "square of 45" }));
    const card = await screen.findByRole("article", { name: "Burmese python" });
    expect(within(card).queryByRole("img")).not.toBeInTheDocument();
    expect(within(card).getByText("No openly licensed photo available")).toBeInTheDocument();
  });

  it("narrows the squares to one species and returns to the list", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await screen.findByRole("button", { name: "square of 45" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Species" }), "Red lionfish (Pterois volitans) · 17");
    expect(screen.queryByRole("button", { name: "square of 45" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "square of 5" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "square of 12" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "square of 12" }));
    await userEvent.click(await screen.findByRole("button", { name: "Back to all squares" }));
    expect(await screen.findByText("Busiest squares")).toBeInTheDocument();
  });

  it("explains an empty park instead of drawing nothing", async () => {
    serve(routes({ "/rpc/hotspot_cells": { cell: 0.05, cells: [] } }));
    wrap(<Hotspots zone="serengeti" />);
    expect(await screen.findByText(/No invasive-species records in Serengeti National Park yet/)).toBeInTheDocument();
    expect(screen.queryByTestId("map")).not.toBeInTheDocument();
  });

  it("offers a retry when the squares cannot be loaded", async () => {
    let calls = 0;
    serve(routes({ "/rpc/hotspot_cells": () => (++calls === 1 ? json({ message: "down" }, 503) : json(hotspots)) }));
    wrap(<Hotspots zone={null} />);
    const alert = await screen.findByRole("alert");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("map")).toBeInTheDocument();
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

describe("Sources storage", () => {
  const MB = 1024 * 1024;
  it("shows how much of the free database is used", async () => {
    serve({ "/source_health": [], "/rpc/storage_status": { db_bytes: 27 * MB, budget_bytes: 500 * MB } });
    wrap(<Sources />);
    expect(await screen.findByText(/of 500 MB/)).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Free-tier database" })).toHaveAttribute("aria-valuenow", "27");
  });

  it("says when the figure is unavailable instead of showing a made-up one", async () => {
    serve({ "/source_health": [] });
    wrap(<Sources />);
    expect(await screen.findByText(/storage figure is unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
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

describe("Overview page", () => {
  const zones = {
    type: "FeatureCollection",
    features: [
      ["bandipur", "Bandipur National Park", 900, 16, 14],
      ["everglades", "Everglades National Park", 3000, 120, 9],
      ["serengeti", "Serengeti National Park", 800, 0, 0],
    ].map(([slug, name, observations, invasive_records, invasive_species]) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { slug, name, group: null, country: "XX", observations, species: 50, invasive_records, invasive_species },
    })),
  };

  it("offers three clear places to start", async () => {
    serve({ "/rpc/zones_geojson": zones, "/zone_reports": [], "/alerts": [] });
    wrap(<Overview />);
    const start = screen.getByRole("navigation", { name: "Where to start" });
    const links = within(start).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["#/hotspots", "#/species", "#/impact"]);
    expect(links[0]).toHaveTextContent("Explore hotspots");
    await screen.findByText("4,700"); // the numbers still load beneath it
  });

  it("adds up the parks and ranks them by invasive records", async () => {
    serve({ "/rpc/zones_geojson": zones, "/zone_reports": [], "/alerts": [] });
    wrap(<Overview />);
    expect(await screen.findByText("4,700")).toBeInTheDocument(); // observations
    expect(screen.getByText("136")).toBeInTheDocument(); // invasive records
    const list = screen.getByRole("list", { name: "Invasive-species records by park" });
    const labels = [...list.querySelectorAll(".bar-label")].map((e) => e.textContent);
    expect(labels).toEqual(["Everglades National Park", "Bandipur National Park", "Serengeti National Park"]);
  });

  it("says when no alert has been raised", async () => {
    serve({ "/rpc/zones_geojson": zones, "/zone_reports": [], "/alerts": [] });
    wrap(<Overview />);
    expect(await screen.findByText(/No early-detection alerts/)).toBeInTheDocument();
  });
});

describe("Alerts page", () => {
  it("explains an empty list in plain terms", async () => {
    serve({ "/alerts": [] });
    wrap(<Alerts />);
    expect(await screen.findByText(/No invasive species has been recorded in any park for the first time/)).toBeInTheDocument();
  });

  it("shows each alert with its severity, park, species and caveat", async () => {
    serve({
      "/alerts": [{
        id: 1, kind: "edrr", severity: "medium", created_at: "2026-10-01T00:00:00Z", window_start: "2025-11-19T00:00:00Z",
        evidence: { records: 1, caveat: "First record in the data sources used here." },
        zones: { slug: "mudumalai", name: "Mudumalai National Park" },
        species: { scientific_name: "Cascabela thevetia", common_name: null },
      }],
    });
    wrap(<Alerts />);
    expect(await screen.findByText("Cascabela thevetia")).toBeInTheDocument();
    expect(screen.getByText("Mudumalai National Park")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText(/1 record so far/)).toBeInTheDocument();
    expect(screen.getByText(/First record in the data sources used here/)).toBeInTheDocument();
  });
});

describe("Species page", () => {
  const report = (slug: string, name: string, species: { species: string; common_name: string | null; records: number }[]) => ({
    computed_at: "2026-10-08T00:00:00Z",
    zones: { slug, name },
    report: {
      zone: slug, observations: 100, species: 10,
      invasive_species: species.map((x) => ({ ...x, first_record: "2020-01-01", last_record: "2024-01-01", sources: 1 })),
      layers: {} as never,
    },
  });
  const finding = {
    id: 1, finding_type: "impact", affected: "mammals", certainty: "review", summary: "Reported to reduce mammals.",
    region_note: "Florida", source_quotes: ["a quote"], citation_text: "A study", citation_url: "https://example.org/a",
    verified_on: "2026-10-08", species: { scientific_name: "Python bivittatus", common_name: "Burmese python" }, zones: null,
  };

  it("lists the species recorded in any park, those with research first", async () => {
    serve({
      "/zone_reports": [
        report("bandipur", "Bandipur National Park", [{ species: "Lantana camara", common_name: "common lantana", records: 3 }]),
        report("everglades", "Everglades National Park", [
          { species: "Python bivittatus", common_name: "Burmese python", records: 40 },
          { species: "Anolis sagrei", common_name: "Brown Anole", records: 2 },
        ]),
      ],
      "/impact_findings": [finding],
      "/mitigation_playbooks": [],
    });
    wrap(<SpeciesPage selected={null} />);
    expect(await screen.findByText(/3 invasive species are recorded in the parks or have cited research/)).toBeInTheDocument();
    const names = (await screen.findAllByRole("link")).map((a) => a.textContent ?? "").filter((t) => /camara|bivittatus|sagrei/.test(t));
    expect(names[0]).toContain("Python bivittatus"); // the one with a cited finding leads
    expect(names).toHaveLength(3);
  });

  it("filters the list as you type", async () => {
    serve({
      "/zone_reports": [report("bandipur", "Bandipur National Park", [
        { species: "Lantana camara", common_name: "common lantana", records: 3 },
        { species: "Senna spectabilis", common_name: null, records: 1 },
      ])],
      "/impact_findings": [],
      "/mitigation_playbooks": [],
    });
    wrap(<SpeciesPage selected={null} />);
    const list = within(await screen.findByRole("region", { name: "Species list" }));
    expect(list.getByText("Lantana camara")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "senna");
    expect(list.queryByText("Lantana camara")).not.toBeInTheDocument();
    expect(list.getByText("Senna spectabilis")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.type(screen.getByRole("searchbox"), "zzz");
    expect(await screen.findByText(/No species match/)).toBeInTheDocument();
  });

  it("shows a species' cited findings and says where it was recorded", async () => {
    serve({
      "/zone_reports": [report("everglades", "Everglades National Park", [
        { species: "Python bivittatus", common_name: "Burmese python", records: 40 }])],
      "/impact_findings": [finding],
      "/mitigation_playbooks": [],
    });
    wrap(<SpeciesPage selected="Python bivittatus" />);
    expect(await screen.findByRole("heading", { name: "Python bivittatus" })).toBeInTheDocument();
    expect(screen.getByText("Reported to reduce mammals.")).toBeInTheDocument();
    expect(screen.getByText("No cited management guidance for this species yet.")).toBeInTheDocument();
    expect(screen.getAllByText("Everglades National Park").length).toBeGreaterThan(0);
  });
});
