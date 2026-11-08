import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LayerResult, ZoneReportRow } from "../api/types";

// The real map needs a browser. This stand-in offers each square as a button, which is all the
// page needs from it: which squares it was given, and a way to choose one.
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
import { Overview, topSpecies } from "./Overview";
import { Sources } from "./Sources";
import { SpeciesPage, buildEntries, sortEntries } from "./SpeciesPage";

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

/** A cited paper's fields, as the database returns them with a finding or a management row. */
const paper = (over = {}) => ({
  citation_text: "Willson, J.D. (2017) Indirect effects of invasive Burmese pythons. Journal of Applied Ecology 54: 1251-1258. doi:10.1111/1365-2664.12844",
  citation_url: "https://doi.org/10.1111/1365-2664.12844",
  citation_doi: "10.1111/1365-2664.12844",
  citation_year: 2017,
  citation_journal: "Journal of Applied Ecology",
  verified_on: "2026-11-09",
  ...over,
});
const finding = (over = {}) => ({
  id: 1, finding_type: "impact", affected: "mammals", certainty: "observational",
  summary: "Mammal numbers fell where pythons were established.",
  region_note: "Everglades National Park, Florida", source_quotes: ["loss or decline of mammals is resulting in trophic cascades"],
  species: { scientific_name: "Python bivittatus", common_name: "Burmese python" }, zones: null,
  ...paper(), ...over,
});
const playbook = (over = {}) => ({
  id: 10, method: "detection", description: "Scent lures did not raise detections.", study_design: "experimental",
  region_note: "Greater Everglades", source_quotes: ["mammalian scent lures alone are insufficient to attract pythons"],
  species: { scientific_name: "Python bivittatus", common_name: "Burmese python" },
  ...paper({ citation_text: "Miller, S. et al. (2025) Mammalian scent lures. Management of Biological Invasions 16: 1147-1159.", citation_doi: "10.3391/mbi.2025.16.4.14", citation_year: 2025 }), ...over,
});

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
      documented: { status: "ok", findings: [], note: "Only what papers report." },
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

  it("names the invasive species recorded, and no count of species that have no paper", async () => {
    const busy = report("Everglades National Park", "everglades");
    busy.report.invasive_species = ["Python bivittatus", "Osteopilus septentrionalis", "Schinus terebinthifolia"].map((species, i) => ({
      species, common_name: null, records: 100 - i, first_record: "2020-01-01", last_record: "2020-01-01", sources: 1,
    }));
    serve({ "/zone_reports": [busy] });
    wrap(<Impact />);
    expect(
      await screen.findByText(/3 invasive species recorded: Python bivittatus, Osteopilus septentrionalis, Schinus terebinthifolia\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/observations of/)).not.toBeInTheDocument(); // totals over every species are not shown
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
    expect(await screen.findByText(/no invasive species with a peer-reviewed paper recorded/)).toBeInTheDocument();
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

  it("shows the correlation, and the squares it was computed from, once the data supports it", async () => {
    serve({
      "/zone_reports": [
        report("Bandipur National Park", "bandipur", {
          cooccurrence: layer("ok", {
            cells_usable: 40, spearman_rho: -0.31, ci95: [-0.52, -0.08], richness_compared_at: 10,
            points: [[0.1, 8.2, 3], [0.4, 5.1, 12]],
          }),
        }),
      ],
    });
    wrap(<Impact />);
    expect(await screen.findByText(/ρ = -0.31/)).toBeInTheDocument();
    expect(screen.getByText(/-0.52 to -0.08/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Native species richness against the invasive share/ })).toBeInTheDocument();
  });

  it("draws the trend as a line chart beside its statistics", async () => {
    const series = [2018, 2019, 2020, 2021, 2022, 2023].map((year, i) => ({
      year, observations: 50, invasive: i, native: 40 - i, invasive_per_observation: i / 50, native_per_observation: (40 - i) / 50,
    }));
    serve({
      "/zone_reports": [
        report("Bandipur National Park", "bandipur", {
          trend: layer("ok", {
            years: [2018, 2023], series,
            invasive_per_observation: { tau: 1, p_value: 0.003, slope: 0.02 },
            native_per_observation: { tau: -1, p_value: 0.003, slope: -0.02 },
          }),
        }),
      ],
    });
    wrap(<Impact />);
    expect(await screen.findByRole("img", { name: /Records per observation by year/ })).toBeInTheDocument();
    expect(screen.getByText("Invasive records per observation", { selector: "td" })).toBeInTheDocument();
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
  const cell = (west: number, species: ReturnType<typeof sp>[], by_year: [number, number][]) => ({
    west, south: 25, east: west + 0.05, north: 25.05,
    records: species.reduce((a, x) => a + x.records, 0), species_count: species.length, species,
    by_year, by_source: { iNaturalist: species.reduce((a, x) => a + x.records, 0) },
  });
  const hotspots = {
    km: 5,
    cells: [
      cell(-80.6, [sp("Python bivittatus", "Burmese python", 40), sp("Osteopilus septentrionalis", "Cuban tree frog", 5)], [[2015, 20], [2024, 25]]),
      cell(-80.5, [sp("Osteopilus septentrionalis", "Cuban tree frog", 12)], [[2020, 12]]),
    ],
  };
  const photo = (over = {}) => ({
    scientific_name: "Python bivittatus", common_name: "Burmese python",
    photo_url: "https://static.example.org/python.jpg", photo_credit: "(c) Wayne Fidler, some rights reserved (CC BY-NC)",
    photo_license: "cc-by-nc", photo_source_url: "https://www.inaturalist.org/photos/1", ...over,
  });
  const sources = [
    { id: 3, name: "iNaturalist", kind: "api", items: 100, license: null, attribution: null, base_url: null, last_run: null, fetched: null, skipped_dupe: null, failed: null, rejected: null },
    { id: 4, name: "USGS NAS", kind: "api", items: 50, license: null, attribution: null, base_url: null, last_run: null, fetched: null, skipped_dupe: null, failed: null, rejected: null },
    { id: 1, name: "GRIIS", kind: "dataset", items: 0, license: null, attribution: null, base_url: null, last_run: null, fetched: null, skipped_dupe: null, failed: null, rejected: null },
  ];
  const routes = (over: Record<string, unknown> = {}) => ({
    "/rpc/zones_geojson": zones,
    "/rpc/hotspot_grid": hotspots,
    "/rpc/invasive_by_year": [{ year: 2015, records: 20 }, { year: 2020, records: 12 }, { year: 2024, records: 25 }],
    "/impact_findings": [finding()],
    "/mitigation_playbooks": [playbook()],
    "/source_health": sources,
    "/species?select": [photo()],
    ...over,
  });

  it("opens on the park with the most invasive records and asks for that park's squares", async () => {
    const fetchMock = serve(routes());
    wrap(<Hotspots zone={null} />);
    expect(await screen.findByTestId("map")).toBeInTheDocument();
    const asked = fetchMock.mock.calls.map(([u]) => String(u)).find((u) => u.includes("hotspot_grid"))!;
    expect(asked).toContain("p_zone=everglades");
    expect(asked).toMatch(/p_km=\d/); // squares are sized in kilometres
    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Park" }).value).toBe("everglades");
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
    expect([...document.querySelectorAll("optgroup")].map((g) => g.label)).toEqual(["India", "Tanzania", "United States"]);
  });

  it("opens on the whole park with the most recorded species first, its first species open", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    expect(await screen.findByText("Whole park")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "57 records" })).toBeInTheDocument(); // 45 + 12
    expect(screen.getByText("2 invasive species.")).toBeInTheDocument();
    const rows = [...document.querySelectorAll("details.species-row")];
    expect(rows.map((r) => r.querySelector("strong")?.textContent)).toEqual(["Burmese python", "Cuban tree frog"]);
    expect((rows[0] as HTMLDetailsElement).open).toBe(true);
    expect((rows[1] as HTMLDetailsElement).open).toBe(false);
  });

  it("shows, for the open species, its photo, credit, record count and the paper behind each effect", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await screen.findByText("Whole park");
    const row = document.querySelector<HTMLElement>("details.species-row")!;
    expect(within(row).getByRole("img", { name: "Photograph of Burmese python" })).toHaveAttribute("src", "https://static.example.org/python.jpg");
    expect(within(row).getByText(/Wayne Fidler/)).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Photo page" })).toHaveAttribute("href", "https://www.inaturalist.org/photos/1");
    expect(within(row).getByText(/Mammal numbers fell where pythons/)).toBeInTheDocument();
    expect(within(row).getByText("Field study")).toBeInTheDocument();
    const cite = within(row).getByRole("link", { name: /Willson, J\.D\. \(2017\)/ });
    expect(cite).toHaveAttribute("href", "https://doi.org/10.1111/1365-2664.12844");
    expect(within(row).getByText(/1 paper on management/)).toBeInTheDocument();
  });

  it("never renders an image address that could run code", async () => {
    serve(routes({ "/species?select": [photo({ photo_url: "javascript:alert(1)" })] }));
    wrap(<Hotspots zone={null} />);
    await screen.findByText("Whole park");
    const row = document.querySelector<HTMLElement>("details.species-row")!;
    expect(within(row).queryByRole("img")).not.toBeInTheDocument();
    expect(within(row).getByText("No openly licensed photo available")).toBeInTheDocument();
  });

  it("follows the square you choose and goes back to the whole park", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await userEvent.click(await screen.findByRole("button", { name: "square of 12" }));
    expect(await screen.findByText("This square")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /° N, .*° W/ })).toBeInTheDocument();
    const rows = [...document.querySelectorAll("details.species-row")];
    expect(rows.map((r) => r.querySelector("strong")?.textContent)).toEqual(["Cuban tree frog"]); // the species in that square
    await userEvent.click(screen.getByRole("button", { name: "Back to all squares" }));
    expect(await screen.findByText("Whole park")).toBeInTheDocument();
  });

  it("narrows the squares to one species by asking the database, which counts it exactly", async () => {
    const onlyFrog = {
      km: 5,
      cells: [
        { ...hotspots.cells[0]!, records: 5, species_count: 1, species: [hotspots.cells[0]!.species[1]!], by_year: [[2019, 5]] },
        hotspots.cells[1]!,
      ],
    };
    const fetchMock = serve(routes({
      "/rpc/hotspot_grid": () => (fetchMock.mock.calls.some(([u]) => String(u).includes("p_species")) ? json(onlyFrog) : json(hotspots)),
    }));
    wrap(<Hotspots zone={null} />);
    await screen.findByRole("button", { name: "square of 45" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Species" }), "Cuban tree frog (Osteopilus septentrionalis) · 17");
    expect(await screen.findByRole("button", { name: "square of 5" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "square of 12" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "square of 45" })).not.toBeInTheDocument();
    const asked = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("p_species")).pop()!;
    expect(asked).toContain("p_species=Osteopilus%20septentrionalis");
    // The species menu still lists every species of the park while one is chosen.
    expect(screen.getByRole("option", { name: /Burmese python/ })).toBeInTheDocument();
  });

  it("asks the database to narrow by source, years and group, and can reset", async () => {
    const fetchMock = serve(routes());
    wrap(<Hotspots zone={null} />);
    await screen.findByTestId("map");
    const lastGrid = () => String(fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("hotspot_grid")).pop());

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Source" }), "iNaturalist");
    await waitFor(() => expect(lastGrid()).toContain("p_sources=iNaturalist"));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "From" }), "2015");
    await waitFor(() => expect(lastGrid()).toContain("p_year_from=2015"));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Group" }), "Plants");
    await waitFor(() => expect(lastGrid()).toContain("p_kingdom=Plantae"));
    expect(lastGrid()).not.toContain("GRIIS"); // a checklist is not a source of records

    // Resetting brings back the unfiltered squares, which the page already holds.
    await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByRole("combobox", { name: "Source" })).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "From" })).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Group" })).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Reset filters" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "square of 45" })).toBeInTheDocument();
  });

  it("states the square size it is using, and offers sizes in kilometres", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await screen.findByTestId("map");
    expect(screen.getByRole("option", { name: /^Automatic \(\d+(\.\d)? km\)$/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "2 km" })).toBeInTheDocument();
    expect(screen.getByText(/57 records in 2 squares, each 5 km on a side\./)).toBeInTheDocument();
  });

  it("has no checkbox for individual records and no list of most recorded species chips", async () => {
    serve(routes());
    wrap(<Hotspots zone={null} />);
    await screen.findByTestId("map");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Most recorded species" })).not.toBeInTheDocument();
  });

  it("explains an empty park instead of drawing nothing", async () => {
    serve(routes({ "/rpc/hotspot_grid": { km: 5, cells: [] } }));
    wrap(<Hotspots zone="serengeti" />);
    expect(await screen.findByText(/No invasive-species records in Serengeti National Park yet/)).toBeInTheDocument();
    expect(screen.queryByTestId("map")).not.toBeInTheDocument();
  });

  it("offers a retry when the squares cannot be loaded", async () => {
    let calls = 0;
    serve(routes({ "/rpc/hotspot_grid": () => (++calls === 1 ? json({ message: "down" }, 503) : json(hotspots)) }));
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
        { ...base, id: 2, name: "Hostile", kind: "api", items: 5, base_url: "javascript:alert(1)" },
      ],
    });
    wrap(<Sources />);
    expect(await screen.findAllByText("checklist")).toHaveLength(2); // its kind and its record column
    expect(screen.getByRole("link", { name: "GRIIS" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Hostile" })).not.toBeInTheDocument(); // shown as text only
    expect(screen.getByText("Hostile")).toBeInTheDocument();
  });

  it("shows the licence without the name of the database column that holds it", async () => {
    serve({ "/source_health": [{ ...base, id: 3, name: "iNaturalist", kind: "api", items: 9, license: "Per record (CC); see media_items.license" }] });
    wrap(<Sources />);
    expect(await screen.findByText("Per record (CC)")).toBeInTheDocument();
    expect(screen.queryByText(/media_items/)).not.toBeInTheDocument();
  });

  it("charts why records were refused, by source", async () => {
    serve({
      "/source_health": [
        { ...base, id: 3, name: "iNaturalist", kind: "api", items: 9, rejected: { outside_zone: 70, invasive_without_paper: 5 } },
        { ...base, id: 4, name: "USGS NAS", kind: "api", items: 4, rejected: null },
      ],
    });
    wrap(<Sources />);
    expect(await screen.findByRole("heading", { name: "Why records were refused" })).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Why iNaturalist records were refused" });
    expect([...list.querySelectorAll(".bar-label")].map((e) => e.textContent)).toEqual(["outside zone", "invasive without paper"]);
    expect(screen.queryByRole("list", { name: "Why USGS NAS records were refused" })).not.toBeInTheDocument();
  });

  it("does not show how full the database is: that is for the people who run it", async () => {
    serve({ "/source_health": [] });
    wrap(<Sources />);
    await screen.findByRole("heading", { name: "Limits of this data" });
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    expect(screen.queryByText(/500 MB/)).not.toBeInTheDocument();
  });

  it("states its limits as facts about the data, with no claim about a particular plant or place", async () => {
    serve({ "/source_health": [] });
    wrap(<Sources />);
    const limits = (await screen.findByRole("heading", { name: "Limits of this data" })).nextElementSibling!;
    expect(limits.textContent).not.toMatch(/Lantana|Senna|Andaman|widely reported|photograph more/);
    expect(limits.textContent).toMatch(/peer-reviewed papers/);
  });
});

describe("species list", () => {
  const sp = (name: string, common: string | null = null) => ({ species: { scientific_name: name, common_name: common } });
  const rep = (species: { species: string; records: number }[]) => ({ report: { invasive_species: species } });

  it("lists only species a paper backs, the most recorded first", () => {
    const entries = buildEntries(
      [{ ...sp("Mmm few records"), ...paper() }] as never,
      [{ id: 1, ...sp("Python bivittatus"), ...paper() }, { id: 2, ...sp("Python bivittatus"), ...paper() }] as never,
      [rep([{ species: "Python bivittatus", records: 40 }, { species: "Mmm few records", records: 2 }, { species: "No paper here", records: 900 }])] as never,
    );
    expect(sortEntries(entries).map((e) => e.name)).toEqual(["Python bivittatus", "Mmm few records"]);
    expect(entries.find((e) => e.name === "No paper here")).toBeUndefined(); // 900 records and still not listed
    expect(entries.find((e) => e.name === "Python bivittatus")).toMatchObject({ records: 40, papers: 2 });
  });

  it("includes a species that has a paper but no records in the parks", () => {
    const entries = buildEntries([], [{ id: 1, ...sp("Only a paper"), ...paper() }] as never, []);
    expect(entries).toEqual([{ name: "Only a paper", common: null, papers: 1, records: 0 }]);
  });

  it("breaks ties by papers, then alphabetically", () => {
    const e = (name: string, records: number, papers: number) => ({ name, common: null, records, papers });
    expect(sortEntries([e("B", 5, 1), e("A", 5, 1), e("C", 5, 3)]).map((x) => x.name)).toEqual(["C", "A", "B"]);
  });
});

describe("Overview page", () => {
  const zones = {
    type: "FeatureCollection",
    features: [
      ["bandipur", "Bandipur National Park", 900, 16, 3],
      ["everglades", "Everglades National Park", 3000, 120, 4],
      ["serengeti", "Serengeti National Park", 800, 0, 0],
    ].map(([slug, name, observations, invasive_records, invasive_species]) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { slug, name, group: null, country: "XX", observations, species: 50, invasive_records, invasive_species },
    })),
  };
  const reports = [
    { ...report("Bandipur National Park", "bandipur") },
    { ...report("Everglades National Park", "everglades") },
  ];
  const routes = {
    "/rpc/zones_geojson": zones,
    "/zone_reports": reports,
    "/impact_findings": [finding(), finding({ id: 2 })],
    "/mitigation_playbooks": [playbook()],
    "/rpc/invasive_by_year": [{ year: 2020, records: 4 }, { year: 2021, records: 9 }],
  };

  it("shows records of species a paper backs, how many species, and how many papers", async () => {
    serve(routes);
    wrap(<Overview />);
    expect(await screen.findByText("136")).toBeInTheDocument(); // invasive records
    expect(screen.getByText("Invasive-species records")).toBeInTheDocument();
    expect(screen.getByText("each backed by a paper")).toBeInTheDocument();
    const tile = screen.getByText("Peer-reviewed papers").closest(".tile") as HTMLElement;
    expect(within(tile).getByText("2")).toBeInTheDocument(); // two distinct papers: both findings cite one, the playbook another
  });

  it("does not show a total of observations of species that have no paper", async () => {
    serve(routes);
    wrap(<Overview />);
    await screen.findByText("136");
    expect(screen.queryByText("Observations")).not.toBeInTheDocument();
    expect(screen.queryByText("4,700")).not.toBeInTheDocument();
  });

  it("ranks the parks by invasive records", async () => {
    serve(routes);
    wrap(<Overview />);
    const list = await screen.findByRole("list", { name: "Invasive-species records by park" });
    expect([...list.querySelectorAll(".bar-label")].map((e) => e.textContent)).toEqual([
      "Everglades National Park", "Bandipur National Park", "Serengeti National Park",
    ]);
  });

  it("charts records by year and names the most recorded species", async () => {
    serve(routes);
    wrap(<Overview />);
    expect(await screen.findByRole("img", { name: /Invasive-species records by year, all parks/ })).toBeInTheDocument();
    expect(await screen.findByRole("list", { name: "Most recorded invasive species, all parks" })).toBeInTheDocument();
  });

  it("repeats nothing that a menu or another page already says", async () => {
    serve(routes);
    wrap(<Overview />);
    await screen.findByText("136");
    expect(screen.queryByRole("navigation", { name: "Where to start" })).not.toBeInTheDocument();
    expect(screen.queryByText(/What the data supports/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Where the records come from/)).not.toBeInTheDocument();
  });

  it("adds up each species across parks for the ranking", () => {
    const park = (species: { species: string; common_name: string | null; records: number }[]) =>
      ({ report: { invasive_species: species.map((s) => ({ ...s, first_record: "", last_record: "", sources: 1 })) } }) as never;
    const top = topSpecies([
      park([{ species: "Python bivittatus", common_name: "Burmese python", records: 40 }, { species: "Lantana camara", common_name: null, records: 3 }]),
      park([{ species: "Lantana camara", common_name: "common lantana", records: 4 }]),
    ]);
    expect(top.map((t) => [t.key, t.value, t.label])).toEqual([
      ["Python bivittatus", 40, "Burmese python"],
      ["Lantana camara", 7, "common lantana"],
    ]);
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
        species: { scientific_name: "Lantana camara", common_name: null },
      }],
    });
    wrap(<Alerts />);
    expect(await screen.findByText("Lantana camara")).toBeInTheDocument();
    expect(screen.getByText("Mudumalai National Park")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText(/1 record so far/)).toBeInTheDocument();
    expect(screen.getByText(/First record in the data sources used here/)).toBeInTheDocument();
  });
});

describe("Species page", () => {
  const report = (slug: string, name: string, species: { species: string; common_name: string | null; records: number }[]) => ({
    computed_at: "2026-11-09T00:00:00Z",
    zones: { slug, name },
    report: {
      zone: slug, observations: 100, species: 10,
      invasive_species: species.map((x) => ({ ...x, first_record: "2020-01-01", last_record: "2024-01-01", sources: 1 })),
      layers: {} as never,
    },
  });
  const profile = {
    records: 40, first_year: 2005, last_year: 2024,
    by_park: [{ slug: "everglades", park: "Everglades National Park", records: 40 }],
    by_year: [{ year: 2005, records: 10 }, { year: 2024, records: 30 }],
    by_source: [{ source: "USGS NAS", records: 40 }],
  };
  const routes = (over: Record<string, unknown> = {}) => ({
    "/zone_reports": [
      report("bandipur", "Bandipur National Park", [{ species: "Lantana camara", common_name: "common lantana", records: 3 }]),
      report("everglades", "Everglades National Park", [
        { species: "Python bivittatus", common_name: "Burmese python", records: 40 },
        { species: "Anolis sagrei", common_name: "Brown Anole", records: 90 },
      ]),
    ],
    "/impact_findings": [
      finding(),
      finding({ id: 2, species: { scientific_name: "Lantana camara", common_name: "common lantana" }, summary: "Lower tree richness where invaded." }),
    ],
    "/mitigation_playbooks": [playbook()],
    "/rpc/species_profile": profile,
    "/species?select": [],
    ...over,
  });

  it("lists only the species a paper backs, not a recorded species that has none", async () => {
    serve(routes());
    wrap(<SpeciesPage selected={null} />);
    expect(await screen.findByText(/2 invasive species, most recorded first/)).toBeInTheDocument();
    const list = within(screen.getByRole("region", { name: "Species list" }));
    expect(list.getByText("Burmese python")).toBeInTheDocument();
    expect(list.getByText("common lantana")).toBeInTheDocument();
    expect(list.queryByText(/Anolis sagrei|Brown Anole/)).not.toBeInTheDocument(); // 90 records, no paper
  });

  it("has no control for showing species that lack research, because none is listed", async () => {
    serve(routes());
    wrap(<SpeciesPage selected={null} />);
    await screen.findByText(/most recorded first/);
    expect(screen.queryByText(/Only species with research/)).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument(); // no sort menu either
    expect(screen.queryByText(/no research on file|no peer-reviewed research/i)).not.toBeInTheDocument();
  });

  it("opens on the most recorded species, with its findings, their paper and how it was recorded", async () => {
    serve(routes());
    wrap(<SpeciesPage selected={null} />);
    expect(await screen.findByRole("heading", { name: "Burmese python" })).toBeInTheDocument();
    expect(screen.getByText("Mammal numbers fell where pythons were established.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Willson, J\.D\. \(2017\)/ })).toHaveAttribute("href", "https://doi.org/10.1111/1365-2664.12844");
    expect(screen.getByRole("heading", { name: "What has been tried" })).toBeInTheDocument();
    expect(screen.getByText(/Scent lures did not raise detections/)).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /Records of Python bivittatus by year/ })).toBeInTheDocument();
    expect(screen.getAllByText("Everglades National Park").length).toBeGreaterThan(0);
  });

  it("leaves out a section when the species has no paper for it", async () => {
    serve(routes());
    wrap(<SpeciesPage selected="Lantana camara" />);
    expect(await screen.findByRole("heading", { name: "common lantana" })).toBeInTheDocument();
    expect(screen.getByText("Lower tree richness where invaded.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What has been tried" })).not.toBeInTheDocument();
  });

  it("says a species is not listed when no paper reports on it", async () => {
    serve(routes());
    wrap(<SpeciesPage selected="Anolis sagrei" />);
    expect(await screen.findByText(/“Anolis sagrei” is not listed: no peer-reviewed paper on file reports on it/)).toBeInTheDocument();
  });

  it("filters the list as you type", async () => {
    serve(routes());
    wrap(<SpeciesPage selected={null} />);
    const list = within(await screen.findByRole("region", { name: "Species list" }));
    expect(list.getByText("Burmese python")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "lantana");
    expect(list.queryByText("Burmese python")).not.toBeInTheDocument();
    expect(list.getByText("common lantana")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.type(screen.getByRole("searchbox"), "zzz");
    expect(await screen.findByText(/No species match/)).toBeInTheDocument();
  });

  it("says a species with a paper is not recorded when no park holds a record", async () => {
    serve(routes({ "/rpc/species_profile": { ...profile, records: 0, first_year: null, last_year: null, by_park: [], by_year: [], by_source: [] } }));
    wrap(<SpeciesPage selected="Python bivittatus" />);
    expect(await screen.findByText(/Not recorded in these parks/)).toBeInTheDocument();
  });
});
