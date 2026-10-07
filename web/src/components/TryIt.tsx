import { useRef, useState } from "react";
import { config } from "../config";
import { fmtPct } from "../lib/format";
import { ErrorState } from "./basics";

type Task = "plants" | "animals";

interface PlantResult {
  answer: string;
  best_guess: string;
  probability: number;
  threshold: number;
  kind: string | null;
  alternatives: { label: string; probability: number }[];
  context: { invasive_in_india: boolean | null; playbooks: number; impact_findings: number } | null;
  notice: string;
}
interface AnimalResult {
  findings: { label: string; confidence: number; species: { answer: string; best_guess: string; probability: number } | null }[];
  notice: string;
}

/**
 * The live demo. It needs the optional API service, which may be asleep (free hosts sleep) or not
 * deployed at all, so every failure is explained rather than left as a spinner.
 */
export function TryIt() {
  const [task, setTask] = useState<Task>("plants");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [plant, setPlant] = useState<PlantResult | null>(null);
  const [animal, setAnimal] = useState<AnimalResult | null>(null);
  const input = useRef<HTMLInputElement>(null);

  if (!config.apiUrl) {
    return (
      <div className="card">
        <p style={{ margin: 0 }}>
          The live photo demo needs the optional analysis service, which is not connected to this deployment.
          The measurements above stand on their own; the demo only lets you try the same models yourself.
        </p>
      </div>
    );
  }

  async function run() {
    const file = input.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setPlant(null);
    setAnimal(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${config.apiUrl}/api/v1/infer/${task}`, { method: "POST", body });
      if (!res.ok) {
        const detail = ((await res.json().catch(() => ({}))) as { detail?: string }).detail;
        throw new Error(
          res.status === 429
            ? "Too many requests. Wait a minute and try again."
            : res.status === 503
              ? "That model is not available on the server right now."
              : (detail ?? `The service answered ${res.status}.`),
        );
      }
      if (task === "plants") setPlant((await res.json()) as PlantResult);
      else setAnimal((await res.json()) as AnimalResult);
    } catch (e) {
      setError(
        e instanceof TypeError
          ? new Error("Could not reach the analysis service. If it was idle it may take about a minute to wake: try again shortly.")
          : e,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="filters" role="group" aria-label="Photo analysis">
        <label>
          Analyse
          <select value={task} onChange={(e) => setTask(e.target.value as Task)}>
            <option value="plants">a plant (invasive or look-alike?)</option>
            <option value="animals">a camera-trap photo (what animals?)</option>
          </select>
        </label>
        <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Choose a photo" />
        <button className="btn primary" disabled={busy} onClick={() => void run()}>
          {busy ? "Analysing…" : "Analyse"}
        </button>
      </div>
      <p className="hint" style={{ marginTop: 0 }}>
        Your photo is analysed in memory and not stored. People in camera-trap photos are detected but never cropped or classified.
        The first request after a quiet spell can take about a minute.
      </p>
      {error != null && <ErrorState error={error} />}
      {plant && <PlantAnswer r={plant} />}
      {animal && <AnimalAnswer r={animal} />}
    </div>
  );
}

function PlantAnswer({ r }: { r: PlantResult }) {
  return (
    <div role="status">
      <p style={{ fontSize: 17, margin: "4px 0" }}>
        {r.answer === "unknown" ? (
          <>
            <strong>Not sure.</strong> It leans towards <em>{r.best_guess}</em> ({fmtPct(r.probability, 0)}), below the {r.threshold.toFixed(2)} needed to name it.
          </>
        ) : r.answer === "other_plant" ? (
          <>
            <strong>None of the listed plants</strong> ({fmtPct(r.probability, 0)}).
          </>
        ) : (
          <>
            <strong><em>{r.answer}</em></strong> ({fmtPct(r.probability, 0)}){r.kind === "invasive" ? ", an invasive species" : r.kind === "native_lookalike" ? ", a native look-alike" : ""}.
          </>
        )}
      </p>
      <p className="where">
        Next most likely: {r.alternatives.slice(1).map((a) => `${a.label} ${fmtPct(a.probability, 0)}`).join(", ")}.
      </p>
      {r.context && (
        <p className="where">
          {r.context.invasive_in_india ? "Flagged invasive in India." : ""} {r.context.impact_findings} cited findings and {r.context.playbooks} management options on record. <a href="#/species">Browse species</a>.
        </p>
      )}
      <p className="hint">{r.notice}</p>
    </div>
  );
}

function AnimalAnswer({ r }: { r: AnimalResult }) {
  return (
    <div role="status">
      {r.findings.length === 0 ? (
        <p>No animals, people or vehicles found.</p>
      ) : (
        <ul>
          {r.findings.map((f, i) => (
            <li key={i}>
              <strong>{f.label}</strong> ({fmtPct(f.confidence, 0)})
              {f.species && (
                <>
                  : {f.species.answer === "unknown" ? <>not sure, leans <em>{f.species.best_guess}</em></> : <em>{f.species.answer}</em>} ({fmtPct(f.species.probability, 0)})
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="hint">{r.notice}</p>
    </div>
  );
}
