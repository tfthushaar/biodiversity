import type { ReactNode } from "react";
import type { Certainty, Playbook } from "../api/types";
import { fmtInt, humanise } from "../lib/format";
import { CertaintyBadge, EvidenceBadge } from "./basics";
import { EvidenceDetails } from "./evidence";

export interface FindingView {
  species: string;
  commonName: string | null;
  certainty: Certainty;
  findingType: string;
  summary: string;
  affected: string;
  regionNote: string;
  quotes: string[];
  citation: string;
  url: string;
  verifiedOn: string | null;
  recordsHere?: number | null;
  zone?: string | null;
  showSpecies?: boolean;
}

/** A cited finding: what it says, how firmly, where the evidence is from, and the exact words. */
export function FindingCard({ f }: { f: FindingView }) {
  return (
    <article className="evidence">
      <div className="head">
        {f.showSpecies !== false && (
          <>
            <strong>
              <em>{f.species}</em>
            </strong>
            {f.commonName && <span className="muted">({f.commonName})</span>}
          </>
        )}
        <CertaintyBadge certainty={f.certainty} />
        <span className="badge">{humanise(f.findingType)}</span>
        {f.zone && <span className="badge">{f.zone}</span>}
        {f.recordsHere != null && f.recordsHere > 0 && (
          <span className="badge">
            {fmtInt(f.recordsHere)} {f.recordsHere === 1 ? "record" : "records"} here
          </span>
        )}
      </div>
      <p style={{ margin: "4px 0" }}>{f.summary}</p>
      <p className="where">
        <strong>Affects:</strong> {f.affected}. <strong>Evidence from:</strong> {f.regionNote}
      </p>
      <EvidenceDetails quotes={f.quotes} citation={f.citation} url={f.url} verifiedOn={f.verifiedOn} />
    </article>
  );
}

const METHOD: Record<string, string> = {
  mechanical: "Mechanical removal",
  chemical: "Chemical control",
  biological: "Biological control",
  cultural: "Use and community-based",
  fire: "Fire",
  grazing: "Grazing",
  integrated: "Integrated / combined",
};

/**
 * One management option as the sources report it. Failures are shown as prominently as
 * successes, and the region the evidence comes from is stated up front, so a result from a
 * Pacific island or an arid grassland is never read as an Indian forest result.
 */
export function PlaybookCard({ p, children }: { p: Playbook; children?: ReactNode }) {
  return (
    <article className="evidence">
      <div className="head">
        <strong>{METHOD[p.method] ?? humanise(p.method)}</strong>
        <EvidenceBadge label="Worked" level={p.effectiveness} />
        <EvidenceBadge label="Evidence" level={p.evidence_strength} />
        {p.cost_tier && <span className="badge">cost: {p.cost_tier}</span>}
      </div>
      <p style={{ margin: "4px 0" }}>{p.description}</p>
      <p className="where">
        <strong>Evidence from:</strong> {p.region_note ?? "not stated"}
      </p>
      {p.failure_cases && (
        <div className="callout fail">
          <strong>What went wrong:</strong> {p.failure_cases}
        </div>
      )}
      {p.risks && (
        <p className="where">
          <strong>Risks and limits:</strong> {p.risks}
        </p>
      )}
      <EvidenceDetails quotes={p.source_quotes} citation={p.citation_text} url={p.citation_url} verifiedOn={p.verified_on} />
      {children}
    </article>
  );
}
