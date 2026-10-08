import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorState, Meter, QueryView, StatTile } from "./basics";
import { BarList, LineChart, type LineSeries } from "./charts";
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
    expect(container.querySelector("svg")).toHaveFocus();
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
