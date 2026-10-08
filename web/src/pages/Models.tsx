import type { ReactNode } from "react";
import { useModels } from "../api/hooks";
import type { ModelVersion, Rate, TradeoffRow } from "../api/types";
import { ErrorState, Loading, StatTile } from "../components/basics";
import { LineChart, type LineSeries } from "../components/charts";
import { TryIt } from "../components/TryIt";
import { fmtInt, fmtPct } from "../lib/format";

const pct = (v: number) => `${Math.round(v * 100)}%`;
const interval = (r?: Rate) => (r ? `95% interval ${fmtPct(r.ci95[0], 1)} to ${fmtPct(r.ci95[1], 1)}` : "");
const counts = (r?: Rate) => (r ? `${fmtInt(r.count)} of ${fmtInt(r.of)}` : "–");

export function Models() {
  const models = useModels();
  const by = (task: ModelVersion["task"]) => models.data?.find((m) => m.task === task);
  return (
    <>
      <h1>Models and how well they work</h1>
      <p className="lede">
        Every figure on this page was measured on photos that were held out of training. The measurements are
        stored alongside each model, with the limits that apply to them.
      </p>
      {models.isError && !models.data ? (
        <ErrorState error={models.error} onRetry={() => void models.refetch()} />
      ) : !models.data ? (
        <Loading what="models" />
      ) : (
        <>
          <PlantSection m={by("plant_classifier")} />
          <AnimalSection m={by("animal_classifier")} />
          <DetectorSection m={by("detector")} />
        </>
      )}
      <h2>Try it on a photo</h2>
      <TryIt />
    </>
  );
}

function Caveats({ items }: { items: string[] | undefined }) {
  if (!items?.length) return null;
  return (
    <div className="callout fail">
      <strong>Limits</strong>
      <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
        {items.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </div>
  );
}

function Section({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <h2>{title}</h2>
      <p className="muted" style={{ marginTop: -4 }}>{intro}</p>
      {children}
    </section>
  );
}

function curve(rows: TradeoffRow[] | undefined, pick: (r: TradeoffRow) => number | null | undefined) {
  return (rows ?? []).map((r) => ({ x: r.threshold, y: pick(r) ?? null }));
}

function PlantSection({ m }: { m?: ModelVersion }) {
  if (!m) return null;
  const x = m.metrics;
  const rows = x.threshold_tradeoff_on_test;
  const series: LineSeries[] = [
    { id: "named", label: "Photos named", short: "Photos named", color: "var(--series-1)", points: curve(rows, (r) => r.answered) },
    { id: "inv", label: "Invasives correctly named", short: "Invasives named", color: "var(--series-2)", dash: "8 5", points: curve(rows, (r) => r.invasives_named?.rate) },
    { id: "other", label: "Other plants called invasive", short: "Others flagged", color: "var(--series-3)", dash: "2 5", points: curve(rows, (r) => r.non_target_called_invasive?.other?.rate) },
  ];
  const look = x.dangerous_errors_by_kind?.native_lookalike;
  const other = x.dangerous_errors_by_kind?.other;
  return (
    <Section
      title="Invasive-plant classifier"
      intro={
        <>
          Names one of {x.classes ? x.classes.length - 1 : "–"} plants (ten invasives and native look-alikes) or says “unknown”.
          Tested on {fmtInt(x.test_photos)} photos by photographers it had never seen.
        </>
      }
    >
      <div className="grid" aria-label="Plant classifier results">
        <StatTile label="Right, when it names a plant" value={fmtPct(x.accuracy_when_answered)} sub={`names ${fmtPct(x.answered, 0)} of photos; the rest are “unknown”`} />
        <StatTile label="Invasives correctly named" value={fmtPct(x.invasives_correctly_named?.rate)} sub={`${counts(x.invasives_correctly_named)} · ${interval(x.invasives_correctly_named)}`} />
        <StatTile label="Native look-alikes called invasive" value={counts(look)} sub={interval(look)} />
        <StatTile label="Other plants called invasive" value={fmtPct(other?.rate)} sub={`${counts(other)} · ${interval(other)}`} />
      </div>

      <h3 style={{ marginTop: 20 }}>The threshold trades coverage for caution</h3>
      <div className="card">
        <p className="hint" style={{ marginTop: 0 }}>
          Raising the confidence needed before it names a plant makes it name fewer plants and wrongly call far
          fewer other plants invasive. The deployed threshold is {x.chosen?.threshold.toFixed(2)}, set on separate
          validation data before these results were measured.
        </p>
        <LineChart
          series={series}
          caption="Plant classifier: effect of the confidence threshold"
          xLabel="Confidence threshold"
          xFormat={(v) => v.toFixed(2)}
          yFormat={pct}
        />
      </div>
      <Caveats items={x.caveats} />
    </Section>
  );
}

function AnimalSection({ m }: { m?: ModelVersion }) {
  if (!m) return null;
  const x = m.metrics;
  const rows = x.threshold_tradeoff_on_test;
  const series: LineSeries[] = [
    { id: "named", label: "Crops named", short: "Named", color: "var(--series-1)", points: curve(rows, (r) => r.answered) },
    { id: "right", label: "Right, when named", short: "Right", color: "var(--series-2)", dash: "8 5", points: curve(rows, (r) => r.accuracy_when_answered) },
  ];
  const gap = x.same_cameras_top1 != null && x.new_cameras_top1 != null ? x.same_cameras_top1 - x.new_cameras_top1 : null;
  return (
    <Section
      title="Camera-trap animal classifier"
      intro={<>Identifies 13 North American species from Caltech Camera Traps. It demonstrates the pipeline and measures how well a classifier transfers to cameras it was not trained on.</>}
    >
      <div className="grid" aria-label="Animal classifier results">
        <StatTile label="Accuracy on cameras never seen" value={fmtPct(x.new_cameras_top1)} sub={`${fmtInt(x.test_photos)} crops · baseline ${fmtPct(x.majority_class_baseline, 0)}`} />
        <StatTile label="…with the same cameras on both sides" value={fmtPct(x.same_cameras_top1)} sub={gap != null ? `unseen cameras cost ${(gap * 100).toFixed(1)} points` : undefined} />
        <StatTile label="Right, when it names an animal" value={fmtPct(x.accuracy_when_answered)} sub={`names ${fmtPct(x.answered, 0)} of crops`} />
      </div>
      <h3 style={{ marginTop: 20 }}>Coverage against reliability</h3>
      <div className="card">
        <LineChart
          series={series}
          caption="Animal classifier: effect of the confidence threshold"
          xLabel="Confidence threshold"
          xFormat={(v) => v.toFixed(2)}
          yFormat={pct}
        />
      </div>
      <Caveats items={x.caveats} />
    </Section>
  );
}

function DetectorSection({ m }: { m?: ModelVersion }) {
  if (!m) return null;
  const x = m.metrics;
  const rows = x.image_level_by_threshold ?? [];
  const at = (t: number) => rows.find((r) => r.threshold === t);
  const r02 = at(0.2);
  const series: LineSeries[] = [
    { id: "recall", label: "Animal photos found", short: "Found", color: "var(--series-1)", points: rows.map((r) => ({ x: r.threshold, y: r.recall })) },
    { id: "precision", label: "Flagged photos with an animal", short: "Precision", color: "var(--series-2)", dash: "8 5", points: rows.map((r) => ({ x: r.threshold, y: r.precision })) },
    { id: "fa", label: "Empty photos flagged (upper bound)", short: "Empty flagged", color: "var(--series-3)", dash: "2 5", points: rows.map((r) => ({ x: r.threshold, y: r.false_alarm_rate })) },
  ];
  return (
    <Section
      title="Detector (MegaDetector V6)"
      intro={<>Finds animals, people and vehicles in a camera-trap frame. Tested on {fmtInt(x.images)} real Caltech Camera Traps photos against human-drawn labels.</>}
    >
      <div className="grid" aria-label="Detector results at threshold 0.2">
        <StatTile label="Animal photos found" value={fmtPct(r02?.recall)} sub="at confidence 0.2" />
        <StatTile label="Flagged photos that had an animal" value={fmtPct(r02?.precision)} sub="at confidence 0.2" />
        <StatTile label="Empty photos flagged" value={fmtPct(r02?.false_alarm_rate)} sub="an upper bound: see below" />
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <LineChart
          series={series}
          caption="Detector: effect of the confidence threshold"
          xLabel="Confidence threshold"
          xFormat={(v) => v.toFixed(1)}
          yFormat={pct}
        />
      </div>
      <Caveats
        items={[
          x.caveat ?? "",
          "Tested on US Southwest camera traps. How well it transfers to Indian or African habitats is unmeasured.",
        ].filter(Boolean)}
      />
    </Section>
  );
}
