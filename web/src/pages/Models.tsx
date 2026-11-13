import type { ReactNode } from "react";
import { useModels } from "../api/hooks";
import type { ModelVersion, Rate, TradeoffRow } from "../api/types";
import { ErrorState, Loading, StatTile } from "../components/basics";
import { BarList, LineChart, RateRanges, ShareBars, type LineSeries, type RateRow } from "../components/charts";
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

/** A titled chart with a line of plain words saying what it shows. */
function Figure({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="card figure">
      <h3>{title}</h3>
      {hint && <p className="hint" style={{ marginTop: 0 }}>{hint}</p>}
      {children}
    </section>
  );
}

/** The curves behind the deployed setting, kept out of the way until a reader asks for them. */
function SettingCurves({ intro, children }: { intro: ReactNode; children: ReactNode }) {
  return (
    <details className="card more wide">
      <summary>How the confidence setting changes this</summary>
      <p className="hint">{intro}</p>
      {children}
    </details>
  );
}

const fraction = (v: number | null | undefined) => (typeof v === "number" ? v : 0);

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
  const named = fraction(x.answered);
  const right = fraction(x.accuracy_when_answered);
  const rates: RateRow[] = [
    x.invasives_correctly_named && {
      key: "inv", label: "Invasive plants correctly named", rate: fraction(x.invasives_correctly_named.rate),
      low: x.invasives_correctly_named.ci95[0], high: x.invasives_correctly_named.ci95[1],
      note: `${counts(x.invasives_correctly_named)} photos of invasive plants`, goal: "higher" as const,
    },
    look && {
      key: "look", label: "Native look-alikes called invasive", rate: fraction(look.rate), low: look.ci95[0], high: look.ci95[1],
      note: `${counts(look)} photos of native look-alikes`, goal: "lower" as const,
    },
    other && {
      key: "other", label: "Other plants called invasive", rate: fraction(other.rate), low: other.ci95[0], high: other.ci95[1],
      note: `${counts(other)} photos of other plants`, goal: "lower" as const,
    },
  ].filter((r): r is RateRow => !!r);
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
      <div className="stack">
        <div className="grid stats" aria-label="Plant classifier results">
          <StatTile label="Right, when it names a plant" value={fmtPct(x.accuracy_when_answered)} sub={`names ${fmtPct(x.answered, 0)} of photos; the rest are “unknown”`} />
          <StatTile label="Invasives correctly named" value={fmtPct(x.invasives_correctly_named?.rate)} sub={`${counts(x.invasives_correctly_named)} · ${interval(x.invasives_correctly_named)}`} />
          <StatTile label="Native look-alikes called invasive" value={counts(look)} sub={interval(look)} />
          <StatTile label="Other plants called invasive" value={fmtPct(other?.rate)} sub={`${counts(other)} · ${interval(other)}`} />
        </div>
        <div className="grid figs">
          <Figure title="What happens to 100 test photos" hint="Photos it is not sure about are left as “unknown” and never guessed.">
            <ShareBars
              caption="Plant classifier: outcome of each test photo"
              rows={[{
                key: "photos", label: "All test photos",
                segments: [
                  { key: "right", label: "named correctly", share: named * right, tone: "good" },
                  { key: "wrong", label: "named wrongly", share: named * (1 - right), tone: "bad" },
                  { key: "unknown", label: "left as “unknown”", share: 1 - named, tone: "other" },
                ],
              }]}
            />
          </Figure>
          {rates.length > 0 && (
            <Figure title="How far each rate can be trusted" hint="The dot is what was measured. The bar is the range the true value could lie in, which is wider when there were fewer photos.">
              <RateRanges caption="Plant classifier: rates with their 95% intervals" rows={rates} />
            </Figure>
          )}
          <Figure title="Accuracy compared with guessing" hint="Across all 15 classes, counting every photo, before any is left as “unknown”.">
            <BarList
              caption="Plant classifier accuracy against always guessing the most common class"
              valueLabel="Accuracy"
              max={1}
              items={[
                { key: "model", label: "The classifier", value: fraction(x.test_top1_without_threshold), display: fmtPct(x.test_top1_without_threshold) },
                { key: "guess", label: "Always guessing the most common plant", value: fraction(x.majority_class_baseline), display: fmtPct(x.majority_class_baseline) },
              ]}
            />
          </Figure>
          <SettingCurves intro={<>Raising the confidence needed before it names a plant makes it name fewer plants and wrongly call far fewer other plants invasive. The setting in use, {x.chosen?.threshold.toFixed(2)}, was chosen on separate validation data before these results were measured.</>}>
            <LineChart
              series={series}
              caption="Plant classifier: effect of the confidence threshold"
              xLabel="Confidence needed before it answers"
              xFormat={(v) => v.toFixed(2)}
              yFormat={pct}
              marker={x.chosen ? { x: x.chosen.threshold, label: `Setting in use (${x.chosen.threshold.toFixed(2)})` } : undefined}
            />
          </SettingCurves>
        </div>
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
  const named = fraction(x.answered);
  const right = fraction(x.accuracy_when_answered);
  return (
    <Section
      title="Camera-trap animal classifier"
      intro={<>Identifies 13 North American species from Caltech Camera Traps. It demonstrates the pipeline and measures how well a classifier transfers to cameras it was not trained on.</>}
    >
      <div className="stack">
        <div className="grid stats" aria-label="Animal classifier results">
          <StatTile label="Accuracy on cameras never seen" value={fmtPct(x.new_cameras_top1)} sub={`${fmtInt(x.test_photos)} crops · baseline ${fmtPct(x.majority_class_baseline, 0)}`} />
          <StatTile label="…with the same cameras on both sides" value={fmtPct(x.same_cameras_top1)} sub={gap != null ? `unseen cameras cost ${(gap * 100).toFixed(1)} points` : undefined} />
          <StatTile label="Right, when it names an animal" value={fmtPct(x.accuracy_when_answered)} sub={`names ${fmtPct(x.answered, 0)} of crops`} />
        </div>
        <div className="grid figs">
          <Figure title="What happens to 100 animal crops" hint="Crops it is not sure about are left as “unknown” and never guessed.">
            <ShareBars
              caption="Animal classifier: outcome of each test crop"
              rows={[{
                key: "crops", label: "All test crops, from cameras it had never seen",
                segments: [
                  { key: "right", label: "named correctly", share: named * right, tone: "good" },
                  { key: "wrong", label: "named wrongly", share: named * (1 - right), tone: "bad" },
                  { key: "unknown", label: "left as “unknown”", share: 1 - named, tone: "other" },
                ],
              }]}
            />
          </Figure>
          <Figure title="Accuracy compared with guessing" hint="Across all 13 species, counting every crop, before any is left as “unknown”.">
            <BarList
              caption="Animal classifier accuracy on new and familiar cameras, against always guessing the most common species"
              valueLabel="Accuracy"
              max={1}
              items={[
                { key: "same", label: "Cameras it had seen before", value: fraction(x.same_cameras_top1), display: fmtPct(x.same_cameras_top1), note: "Near-identical burst frames can fall on both sides, so part of the lead over unseen cameras is leakage." },
                { key: "new", label: "Cameras it had never seen", value: fraction(x.new_cameras_top1), display: fmtPct(x.new_cameras_top1) },
                { key: "guess", label: "Always guessing the most common animal", value: fraction(x.majority_class_baseline), display: fmtPct(x.majority_class_baseline) },
              ]}
            />
          </Figure>
          <SettingCurves intro={<>Raising the confidence needed before it names an animal makes it name fewer crops and be right more often. The setting in use is {x.chosen?.threshold.toFixed(2)}.</>}>
            <LineChart
              series={series}
              caption="Animal classifier: effect of the confidence threshold"
              xLabel="Confidence needed before it answers"
              xFormat={(v) => v.toFixed(2)}
              yFormat={pct}
              marker={x.chosen ? { x: x.chosen.threshold, label: `Setting in use (${x.chosen.threshold.toFixed(2)})` } : undefined}
            />
          </SettingCurves>
        </div>
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
  const found = fraction(r02?.recall);
  const precise = fraction(r02?.precision);
  const flagged = fraction(r02?.false_alarm_rate);
  return (
    <Section
      title="Detector (MegaDetector V6)"
      intro={<>Finds animals, people and vehicles in a camera-trap frame. Tested on {fmtInt(x.images)} real Caltech Camera Traps photos against human-drawn labels.</>}
    >
      <div className="stack">
        <div className="grid stats" aria-label="Detector results at threshold 0.2">
          <StatTile label="Animal photos found" value={fmtPct(r02?.recall)} sub="at confidence 0.2" />
          <StatTile label="Flagged photos that had an animal" value={fmtPct(r02?.precision)} sub="at confidence 0.2" />
          <StatTile label="Empty photos flagged" value={fmtPct(r02?.false_alarm_rate)} sub="an upper bound: see below" />
        </div>
        <div className="grid figs">
          <Figure title="What it does with 100 photos" hint="At confidence 0.2, the setting the figures on this page use. Each bar is a different group of photos.">
            <ShareBars
              caption="Detector: what happens to photos with an animal, photos it flags, and empty photos"
              rows={[
                {
                  key: "animal", label: "Of photos that have an animal",
                  segments: [
                    { key: "found", label: "found", share: found, tone: "good" },
                    { key: "missed", label: "missed", share: 1 - found, tone: "bad" },
                  ],
                },
                {
                  key: "flagged", label: "Of photos it flags as having an animal",
                  segments: [
                    { key: "had", label: "had an animal", share: precise, tone: "good" },
                    { key: "none", label: "had none", share: 1 - precise, tone: "bad" },
                  ],
                },
                {
                  key: "empty", label: "Of photos with nothing in them (upper bound)",
                  segments: [
                    { key: "left", label: "left alone", share: 1 - flagged, tone: "good" },
                    { key: "flag", label: "flagged anyway", share: flagged, tone: "bad" },
                  ],
                },
              ]}
            />
          </Figure>
          <SettingCurves intro={<>Raising the confidence needed before it flags a photo finds fewer animal photos and raises fewer false alarms. The figures above are at 0.2.</>}>
            <LineChart
              series={series}
              caption="Detector: effect of the confidence threshold"
              xLabel="Confidence needed before it flags a photo"
              xFormat={(v) => v.toFixed(1)}
              yFormat={pct}
              marker={{ x: 0.2, label: "Setting in the figures above (0.2)" }}
            />
          </SettingCurves>
        </div>
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
