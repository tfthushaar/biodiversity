import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorState, Meter, QueryView, StatTile } from "./basics";
import { BarList, ColumnChart, GroupedDots, IntervalPlot, LineChart, RateRanges, ShareBars, TrendDots, type LineSeries } from "./charts";
import { FindingCard, PlaybookCard } from "./cards";
import { Citation } from "./evidence";
import { safeUrl } from "./evidence";

describe("StatTile", () => {
  it("shows the label, the number and its context", () => {
    render(<StatTile label="Observations" value="2,373" sub="across 4 zones" />);
    expect(screen.getByText("Observations")).toBeInTheDocument();
    expect(screen.getByText("2,373")).toBeInTheDocument();
    expect(screen.getByText("across 4 zones")).toBeInTheDocument();
  });
});

describe("Meter", () => {
  it("says how far a count is from what a method needs, in words and as a meter", () => {
    render(<Meter label="Invasive records" value={8} target={30} unit="records" />);
    expect(screen.getByText(/of 30 records/)).toBeInTheDocument();
    const meter = screen.getByRole("meter", { name: "Invasive records" });
    expect(meter).toHaveAttribute("aria-valuenow", "8");
    expect(meter).toHaveAttribute("aria-valuemax", "30");
  });

  it("does not print an odd 'of' sentence once the requirement is met", () => {
    render(<Meter label="Years" value={9} target={6} unit="years" />);
    expect(screen.getByText(/6 needed, met/)).toBeInTheDocument();
    expect(screen.queryByText(/9 of 6/)).not.toBeInTheDocument();
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "6"); // never past the end
  });
});

describe("Meter as a limit", () => {
  it("never calls a full ceiling 'met': reaching a limit is not success", () => {
    render(<Meter label="Database" value={500} target={500} unit="MB" limit />);
    expect(screen.getByText(/of 500 MB/)).toBeInTheDocument();
    expect(screen.queryByText(/met/)).not.toBeInTheDocument();
  });
});

describe("QueryView", () => {
  function Probe({ fn }: { fn: () => Promise<string> }) {
    const query = useQuery({ queryKey: ["probe"], queryFn: fn, retry: false });
    return (
      <QueryView query={query} what="the probe">
        {(d) => <p>got {d}</p>}
      </QueryView>
    );
  }
  const wrap = (ui: React.ReactElement) =>
    render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

  it("moves from loading to the data", async () => {
    wrap(<Probe fn={() => Promise.resolve("ok")} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the probe");
    expect(await screen.findByText("got ok")).toBeInTheDocument();
  });

  it("explains a failure and offers a retry", async () => {
    const fn = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce("second try");
    wrap(<Probe fn={fn} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("load this");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("got second try")).toBeInTheDocument();
  });

  it("ErrorState shows a readable message for any thrown value", () => {
    render(<ErrorState error={new Error("The data service answered 503.")} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("BarList", () => {
  const items = [
    { key: "a", label: "Bandipur", value: 8, note: "2020 to 2025" },
    { key: "b", label: "Serengeti", value: 0 },
  ];

  it("draws nothing for a zero, so none never looks like a little", () => {
    const { container } = render(<BarList items={items} caption="Records by zone" valueLabel="Records" />);
    const rows = container.querySelectorAll(".bar-row");
    expect(rows[0]!.querySelector(".bar-fill")).not.toBeNull();
    expect(rows[1]!.querySelector(".bar-fill")).toBeNull();
    expect(rows[1]).toHaveTextContent("0"); // the value is still printed
  });

  it("has a table twin carrying every value", () => {
    render(<BarList items={items} caption="Records by zone" valueLabel="Records" />);
    const table = screen.getByRole("table", { hidden: true, name: "Records by zone" });
    expect(within(table).getByText("Serengeti")).toBeInTheDocument();
    expect(within(table).getByText("2020 to 2025")).toBeInTheDocument();
  });

  it("shows its tooltip on keyboard focus, not only on hover", async () => {
    const { container } = render(<BarList items={items} caption="Records by zone" valueLabel="Records" />);
    await userEvent.tab();
    const tip = container.querySelector(".tooltip");
    expect(tip).not.toBeNull();
    expect(tip).toHaveTextContent("Bandipur");
    expect(tip).toHaveTextContent("2020 to 2025");
    await userEvent.tab(); // moves on: the first tooltip is replaced
    expect(container.querySelector(".tooltip")).toHaveTextContent("Serengeti");
  });
});

describe("LineChart", () => {
  const line = (id: string, label: string, ys: number[], short?: string): LineSeries => ({
    id,
    label,
    short,
    color: `var(--${id})`,
    points: ys.map((y, i) => ({ x: 0.5 + i * 0.1, y })),
  });
  const props = {
    caption: "Trade-off",
    xLabel: "Threshold",
    xFormat: (x: number) => x.toFixed(1),
    yFormat: (y: number) => `${Math.round(y * 100)}%`,
  };

  it("always has a legend for two or more series, and none for one", () => {
    const { rerender } = render(
      <LineChart {...props} series={[line("a", "Found", [1, 0.5]), line("b", "Right", [0.2, 0.9])]} />,
    );
    expect(screen.getByRole("list", { name: "Legend" })).toBeInTheDocument();
    rerender(<LineChart {...props} series={[line("a", "Found", [1, 0.5])]} />);
    expect(screen.queryByRole("list", { name: "Legend" })).not.toBeInTheDocument();
  });

  it("uses the short name for direct labels and the full one in the legend", () => {
    const { container } = render(
      <LineChart
        {...props}
        series={[
          line("a", "Invasives correctly named", [0.9, 0.9], "Invasives named"),
          line("b", "Other plants called invasive", [0.1, 0.0], "Others flagged"),
        ]}
      />,
    );
    const direct = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(direct).toContain("Invasives named");
    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent("Invasives correctly named");
  });

  it("drops the direct labels rather than overlap them when line ends are close", () => {
    const { container } = render(
      <LineChart {...props} series={[line("a", "Alpha", [0.5, 0.5], "Alpha"), line("b", "Beta", [0.5, 0.51], "Beta")]} />,
    );
    const direct = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(direct).not.toContain("Alpha");
    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent("Alpha"); // identity is still carried
  });

  it("moves a crosshair with the arrow keys and lists every series at that x", async () => {
    const { container } = render(
      <LineChart {...props} series={[line("a", "Found", [1, 0.5, 0.25]), line("b", "Right", [0.2, 0.9, 0.95])]} />,
    );
    await userEvent.tab();
    expect(container.querySelector("svg.chart")).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    const tip = container.querySelector(".tooltip");
    expect(tip).toHaveTextContent("Threshold: 0.5");
    expect(tip).toHaveTextContent("Found100%");
    await userEvent.keyboard("{End}");
    expect(container.querySelector(".tooltip")).toHaveTextContent("Right95%");
    await userEvent.keyboard("{Home}");
    expect(container.querySelector(".tooltip")).toHaveTextContent("Threshold: 0.5");
  });

  it("has a table twin with a column per series", () => {
    render(<LineChart {...props} series={[line("a", "Found", [1, 0.5]), line("b", "Right", [0.2, 0.9])]} />);
    const table = screen.getByRole("table", { hidden: true, name: "Trade-off" });
    const heads = within(table).getAllByRole("columnheader", { hidden: true });
    expect(heads.map((h) => h.textContent)).toEqual(["Threshold", "Found", "Right"]);
    expect(within(table).getAllByRole("row", { hidden: true })).toHaveLength(3); // header + 2 x-values
  });

  it("shows a gap as a dash and not a zero", () => {
    const gappy: LineSeries = {
      id: "a",
      label: "Found",
      color: "red",
      points: [
        { x: 1, y: 0.5 },
        { x: 2, y: null },
      ],
    };
    render(<LineChart {...props} series={[gappy, line("b", "Right", [0.1, 0.2])]} />);
    const table = screen.getByRole("table", { hidden: true, name: "Trade-off" });
    expect(within(table).getAllByRole("cell", { hidden: true }).map((c) => c.textContent)).toContain("–");
  });
});

describe("safeUrl", () => {
  it("allows web links only", () => {
    expect(safeUrl("https://doi.org/10.1/x")).toBe("https://doi.org/10.1/x");
    expect(safeUrl("http://example.org/a")).toBe("http://example.org/a");
  });
  it("refuses anything that could run code or is not a link", () => {
    const bad = [
      "javascript:alert(1)",
      "JaVaScRiPt:alert(1)",
      "data:text/html,<script>1</script>",
      "vbscript:x",
      "//evil.example",
      "not a url",
      "",
      null,
      undefined,
    ];
    for (const b of bad) expect(safeUrl(b)).toBeUndefined();
  });
});

describe("LineChart axis labels", () => {
  it("labels about eight years along a century of data, not every year", () => {
    const points = Array.from({ length: 100 }, (_, i) => ({ x: 1925 + i, y: i / 100 }));
    const { container } = render(
      <LineChart
        series={[{ id: "a", label: "A", color: "var(--series-1)", points }]}
        caption="A century"
        xLabel="Year"
        xFormat={(x) => String(x)}
        yFormat={(y) => y.toFixed(2)}
      />,
    );
    const labels = [...container.querySelectorAll("svg text")].map((t) => t.textContent ?? "").filter((t) => /^(19|20)\d\d$/.test(t));
    expect(labels.length).toBeGreaterThanOrEqual(7);
    expect(labels.length).toBeLessThanOrEqual(11);
    expect(labels).toContain("2024"); // the last year is always labelled
  });
});

describe("ColumnChart", () => {
  const data = [
    { year: 2018, records: 3 },
    { year: 2020, records: 10 },
    { year: 2021, records: 4 },
  ];

  it("draws one column for each year with records, and reads each year's value in the table view", () => {
    const { container } = render(<ColumnChart data={data} caption="Records by year" />);
    expect(screen.getByRole("img", { name: /Records by year/ })).toBeInTheDocument();
    expect(container.querySelectorAll("path.col")).toHaveLength(3);
    const table = within(screen.getByRole("table"));
    expect(table.getByText("2020")).toBeInTheDocument();
    expect(table.getByText("10")).toBeInTheDocument();
  });

  it("shows a year with no records as a gap, not a column", () => {
    const { container } = render(<ColumnChart data={data} caption="Records by year" />);
    // 2018 to 2021 is four years; 2019 has none.
    expect(container.querySelectorAll("path.col")).toHaveLength(3);
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(5); // header and four years
  });

  it("groups a long record into bins so it never draws hairline columns", () => {
    const long = Array.from({ length: 100 }, (_, i) => ({ year: 1926 + i, records: 1 }));
    const { container } = render(<ColumnChart data={long} caption="A century" />);
    expect(container.querySelectorAll("path.col").length).toBeLessThanOrEqual(24);
    expect(within(screen.getByRole("table")).getAllByRole("row").length).toBeLessThanOrEqual(25);
  });

  it("reads out a column to the keyboard", async () => {
    render(<ColumnChart data={data} caption="Records by year" />);
    screen.getByRole("img", { name: /Records by year/ }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByText("2018", { selector: ".t-head" })).toBeInTheDocument();
    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByText("2019", { selector: ".t-head" })).toBeInTheDocument();
  });

  it("draws nothing for no data", () => {
    const { container } = render(<ColumnChart data={[]} caption="Nothing" />);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("TrendDots", () => {
  const rows = [2018, 2019, 2020, 2021].map((year, i) => ({
    x: year,
    y: i / 10,
    weight: (i + 1) * 20,
    detail: [{ label: "Observations", value: String((i + 1) * 20) }],
  }));
  const props = {
    rows,
    xLabel: "Year",
    yLabel: "Invasive share",
    yFormat: (y: number) => `${Math.round(y * 100)}%`,
    caption: "Invasive share by year",
  };

  it("draws a dot for each year, larger where the year rests on more observations", () => {
    const { container } = render(<TrendDots {...props} />);
    const radii = [...container.querySelectorAll("circle.dot-point")].map((c) => Number(c.getAttribute("r")));
    expect(radii).toHaveLength(4);
    expect(radii).toEqual([...radii].sort((a, b) => a - b));
    expect(radii[3]).toBeGreaterThan(radii[0] as number);
  });

  it("draws the trend line only when one is given", () => {
    const { container, rerender } = render(<TrendDots {...props} />);
    expect(container.querySelector("line.trend-line")).toBeNull();
    rerender(<TrendDots {...props} line={{ slope: 0.1, intercept: -200 }} lineLabel="Theil-Sen trend" />);
    expect(container.querySelector("line.trend-line")).not.toBeNull();
    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent("Theil-Sen trend");
  });

  it("reads a year out to the keyboard, with the observations behind it", async () => {
    const { container } = render(<TrendDots {...props} />);
    screen.getByRole("img", { name: /Invasive share by year/ }).focus();
    await userEvent.keyboard("{ArrowRight}");
    const tip = container.querySelector(".tooltip");
    expect(tip).toHaveTextContent("Year: 2018");
    expect(tip).toHaveTextContent("Observations20");
    await userEvent.keyboard("{End}");
    expect(container.querySelector(".tooltip")).toHaveTextContent("Year: 2021");
  });

  it("lists every year in the table view", () => {
    render(<TrendDots {...props} />);
    const table = within(screen.getByRole("table", { hidden: true }));
    expect(table.getAllByRole("row", { hidden: true })).toHaveLength(5);
    expect(table.getByText("30%", { exact: true })).toBeInTheDocument();
  });

  it("draws nothing for no rows", () => {
    const { container } = render(<TrendDots {...props} rows={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("GroupedDots", () => {
  const groups = [
    { key: "none", label: "None", values: [{ y: 9 }, { y: 10 }, { y: 8 }] },
    { key: "some", label: "2% to 9%", values: [{ y: 7, note: "3 invasive records" }, { y: 9 }] },
  ];
  const props = { groups, xLabel: "Invasive share", yLabel: "Native species", caption: "Richness by invasive share" };

  it("draws a dot for each square and marks the middle of each group", () => {
    const { container } = render(<GroupedDots {...props} />);
    expect(container.querySelectorAll("circle.dot-point")).toHaveLength(5);
    expect(container.querySelectorAll("line.median-line")).toHaveLength(2);
  });

  it("names each group with its size, so a reader can see how much each rests on", () => {
    const { container } = render(<GroupedDots {...props} />);
    const text = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(text).toEqual(expect.arrayContaining(["None", "n = 3", "2% to 9%", "n = 2"]));
  });

  it("gives each group's count, median and range in the table view", () => {
    render(<GroupedDots {...props} />);
    const table = within(screen.getByRole("table", { hidden: true }));
    const cells = table.getAllByRole("cell", { hidden: true }).map((c) => c.textContent);
    expect(cells).toEqual(["None", "3", "9.0", "8.0", "10.0", "2% to 9%", "2", "8.0", "7.0", "9.0"]);
  });

  it("puts every dot in the same place each time it is drawn", () => {
    const place = () =>
      [...render(<GroupedDots {...props} />).container.querySelectorAll("circle.dot-point")].map((c) => c.getAttribute("cx"));
    expect(place()).toEqual(place());
  });

  it("draws nothing without squares", () => {
    const { container } = render(<GroupedDots {...props} groups={[{ key: "x", label: "x", values: [] }]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("IntervalPlot", () => {
  const props = { value: 0.15, low: -0.1, high: 0.4, minNote: "lower where invaded", maxNote: "higher where invaded", caption: "Correlation 0.15" };

  it("draws the estimate and its interval, and says what each end of the scale means", () => {
    const { container } = render(<IntervalPlot {...props} />);
    expect(screen.getByRole("img", { name: "Correlation 0.15" })).toBeInTheDocument();
    expect(container.querySelector("line.interval")).not.toBeNull();
    const text = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(text).toEqual(expect.arrayContaining(["-1", "0", "+1", "lower where invaded", "higher where invaded"]));
  });

  it("draws no interval when there is none", () => {
    const { container } = render(<IntervalPlot {...props} low={null} high={null} />);
    expect(container.querySelector("line.interval")).toBeNull();
  });

  it("stacks the two notes when they would not fit side by side", () => {
    const long = "native richness is lower where invasive records are denser";
    const { container } = render(<IntervalPlot {...props} minNote={long} maxNote={long.replace("lower", "higher")} />);
    const ys = [...container.querySelectorAll("svg text")]
      .filter((t) => /native richness/.test(t.textContent ?? ""))
      .map((t) => t.getAttribute("y"));
    expect(new Set(ys).size).toBe(2);
  });
});

describe("ShareBars", () => {
  const rows = [{
    key: "photos",
    label: "All test photos",
    segments: [
      { key: "right", label: "named correctly", share: 0.785, tone: "good" as const },
      { key: "wrong", label: "named wrongly", share: 0.028, tone: "bad" as const },
      { key: "unknown", label: "left as unknown", share: 0.187, tone: "other" as const },
    ],
  }];

  it("states every figure in words beside the bar, so nothing depends on its colours", () => {
    render(<ShareBars rows={rows} caption="Outcome of each photo" />);
    const list = within(screen.getByRole("list", { name: "Outcome of each photo" }));
    expect(list.getByText("78.5%", { selector: "strong" }).parentElement).toHaveTextContent("78.5% named correctly");
    expect(list.getByText("2.8%", { selector: "strong" }).parentElement).toHaveTextContent("2.8% named wrongly");
    expect(list.getByText("18.7%", { selector: "strong" }).parentElement).toHaveTextContent("18.7% left as unknown");
  });

  it("sizes each segment by its share and tells the fills apart", () => {
    const { container } = render(<ShareBars rows={rows} caption="Outcome" />);
    const segs = [...container.querySelectorAll(".seg")];
    expect(segs.map((e) => (e as HTMLElement).style.flexBasis)).toEqual(["78.5%", "2.8%", "18.7%"]);
    expect(segs.map((e) => e.className)).toEqual(["seg tone-good", "seg tone-bad", "seg tone-other"]);
  });

  it("writes a figure inside a segment only when the segment is wide enough to hold it", () => {
    const { container } = render(<ShareBars rows={rows} caption="Outcome" />);
    const inside = [...container.querySelectorAll(".seg .seg-text")].map((e) => e.textContent);
    expect(inside).toEqual(["78.5%", "18.7%"]);
  });

  it("describes the whole bar to a screen reader", () => {
    render(<ShareBars rows={rows} caption="Outcome" />);
    expect(screen.getByRole("img", { name: "named correctly 78.5%, named wrongly 2.8%, left as unknown 18.7%" })).toBeInTheDocument();
  });

  it("leaves out a segment with nothing in it but still lists it", () => {
    const none = [{ key: "a", label: "Group", segments: [
      { key: "x", label: "found", share: 1, tone: "good" as const },
      { key: "y", label: "missed", share: 0, tone: "bad" as const },
    ] }];
    const { container } = render(<ShareBars rows={none} caption="Outcome" />);
    expect(container.querySelectorAll(".seg")).toHaveLength(1);
    expect(screen.getByText("0.0%", { selector: "strong" }).parentElement).toHaveTextContent("0.0% missed");
  });

  it("gives each outcome, its share and its fill in the table view", () => {
    render(<ShareBars rows={rows} caption="Outcome" />);
    const cells = within(screen.getByRole("table", { hidden: true })).getAllByRole("cell", { hidden: true }).map((c) => c.textContent);
    expect(cells.slice(0, 4)).toEqual(["All test photos", "named correctly", "78.5%", "solid"]);
    expect(cells).toContain("hatched");
  });
});

describe("RateRanges", () => {
  const rows = [
    { key: "inv", label: "Invasive plants correctly named", note: "225 of 265 photos", rate: 0.849, low: 0.801, high: 0.887, goal: "higher" as const },
    { key: "look", label: "Native look-alikes called invasive", note: "0 of 113 photos", rate: 0, low: 0, high: 0.033, goal: "lower" as const },
  ];

  it("says for every rate which way is good", () => {
    render(<RateRanges rows={rows} caption="Rates" />);
    const items = within(screen.getByRole("list", { name: "Rates" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Higher is better.");
    expect(items[1]).toHaveTextContent("Lower is better.");
  });

  it("gives the range the true value is likely to lie in, in words and as a drawn bar", () => {
    const { container } = render(<RateRanges rows={rows} caption="Rates" />);
    expect(screen.getByText(/likely between 80.1% and 88.7%/)).toBeInTheDocument();
    const bars = [...container.querySelectorAll("line.interval")];
    expect(bars).toHaveLength(2);
    for (const b of bars) expect(Number(b.getAttribute("x2"))).toBeGreaterThan(Number(b.getAttribute("x1")));
    // The wider range is the one drawn from the smaller sample.
    const length = (b: Element) => Number(b.getAttribute("x2")) - Number(b.getAttribute("x1"));
    expect(length(bars[0] as Element)).toBeGreaterThan(length(bars[1] as Element));
  });

  it("shares one 0 to 100% scale between the rows", () => {
    const { container } = render(<RateRanges rows={rows} caption="Rates" />);
    const text = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(text).toEqual(["0%", "25%", "50%", "75%", "100%"]);
  });

  it("lists each rate with its range in the table view", () => {
    render(<RateRanges rows={rows} caption="Rates" />);
    const cells = within(screen.getByRole("table", { hidden: true })).getAllByRole("cell", { hidden: true }).map((c) => c.textContent);
    expect(cells.slice(0, 5)).toEqual(["Invasive plants correctly named", "84.9%", "80.1%", "88.7%", "higher"]);
  });
});

describe("LineChart marker", () => {
  const series: LineSeries[] = [
    { id: "a", label: "Named", color: "var(--series-1)", points: [0.3, 0.5, 0.7, 0.9].map((x) => ({ x, y: 1 - x })) },
  ];
  const props = { series, caption: "Effect", xLabel: "Setting", xFormat: (x: number) => x.toFixed(1), yFormat: (y: number) => `${Math.round(y * 100)}%` };

  it("draws a line at the setting in use and names it in the legend", () => {
    const { container } = render(<LineChart {...props} marker={{ x: 0.5, label: "Setting in use (0.5)" }} />);
    expect(container.querySelectorAll("svg.chart line.marker-line")).toHaveLength(1);
    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent("Setting in use (0.5)");
  });

  it("draws no line for a setting outside the chart", () => {
    const { container } = render(<LineChart {...props} marker={{ x: 5, label: "Elsewhere" }} />);
    expect(container.querySelectorAll("svg.chart line.marker-line")).toHaveLength(0);
  });

  it("adds no legend for one series without a marker", () => {
    render(<LineChart {...props} />);
    expect(screen.queryByRole("list", { name: "Legend" })).not.toBeInTheDocument();
  });
});

describe("evidence from a paper", () => {
  const f = {
    species: "Python bivittatus", commonName: "Burmese python", certainty: "experimental" as const, findingType: "impact",
    summary: "Fewer raccoons where pythons are.", affected: "raccoons", regionNote: "Florida", quotes: ["a quote from the abstract"],
    citation: "Willson, J.D. (2017) Indirect effects. Journal of Applied Ecology. doi:10.1/x", url: "https://doi.org/10.1/x",
    verifiedOn: "2026-11-09",
  };

  it("names the study design in words a reader can follow", () => {
    render(<FindingCard f={f} />);
    expect(screen.getByText("Controlled experiment")).toHaveAttribute("title", expect.stringMatching(/changed one thing/));
  });

  it("links the paper by its DOI and says the quotes were checked against the abstract", () => {
    render(<FindingCard f={f} />);
    expect(screen.getByRole("link", { name: /Willson, J\.D\. \(2017\)/ })).toHaveAttribute("href", "https://doi.org/10.1/x");
    expect(screen.getByText(/quotes checked against the abstract 9 Nov 2026/)).toBeInTheDocument();
    expect(screen.getByText("Evidence (1 quote from the paper)")).toBeInTheDocument();
  });

  it("shows a management method with its study design and setting, and no rating of our own", () => {
    render(
      <PlaybookCard
        p={{
          id: 1, method: "chemical", description: "A herbicide cut the grass.", study_design: "experimental",
          region_note: "Oak woodland", source_quotes: ["the herbicide significantly reduced density"],
          citation_text: "Brewer (2026) Restoration. Restoration Ecology.", citation_url: "https://doi.org/10.1111/rec.70322",
          citation_doi: "10.1111/rec.70322", citation_year: 2026, citation_journal: "Restoration Ecology", verified_on: "2026-11-09",
          species: { scientific_name: "Microstegium vimineum", common_name: null },
        }}
      />,
    );
    expect(screen.getByText("Chemical control")).toBeInTheDocument();
    expect(screen.getByText("Controlled experiment")).toBeInTheDocument();
    expect(screen.getByText("Oak woodland")).toBeInTheDocument();
    expect(screen.queryByText(/Worked|Evidence:|cost:|What went wrong|Risks/)).not.toBeInTheDocument();
  });

  it("renders a citation without a link when the address is unsafe", () => {
    render(<Citation text="A paper" url="javascript:alert(1)" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText(/A paper/)).toBeInTheDocument();
  });
});
