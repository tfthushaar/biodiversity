import type { Finding, HotspotSpecies, SpeciesPhoto } from "../api/types";
import { pluralise } from "../lib/format";
import { yearSpan } from "../lib/hotspots";
import { FindingCard } from "./cards";
import { safeUrl } from "./evidence";

/** What the page knows about a species beyond where it was recorded. */
export interface SpeciesLookup {
  photoOf: (name: string) => SpeciesPhoto | undefined;
  findingsOf: (name: string) => Finding[];
  playbooksOf: (name: string) => number;
}

/** The findings a card shows before it points to the species page for the rest. */
const SHOWN = 2;

function Photo({ photo, display, ratio = "wide" }: { photo: SpeciesPhoto | undefined; display: string; ratio?: "wide" | "thumb" }) {
  const image = safeUrl(photo?.photo_url);
  return (
    <div className={ratio === "thumb" ? "thumb" : "photo"}>
      {image ? (
        <img src={image} alt={ratio === "thumb" ? "" : `Photograph of ${display}`} loading="lazy" referrerPolicy="no-referrer" />
      ) : (
        ratio === "wide" && <div className="none">No openly licensed photo available</div>
      )}
    </div>
  );
}

/** The cited research on a species' effects, with a pointer to the rest. */
export function Research({ findings, playbooks, name }: { findings: Finding[]; playbooks: number; name: string }) {
  const shown = findings.slice(0, SHOWN);
  return (
    <>
      {shown.length > 0 && <h4>Effect on the local environment</h4>}
      {shown.length > 0 &&
        shown.map((f) => (
          <FindingCard
            key={f.id}
            f={{
              species: f.species.scientific_name,
              commonName: f.species.common_name,
              certainty: f.certainty,
              findingType: f.finding_type,
              summary: f.summary,
              affected: f.affected,
              regionNote: f.region_note,
              quotes: f.source_quotes,
              citation: f.citation_text,
              url: f.citation_url,
              verifiedOn: f.verified_on,
              showSpecies: false,
            }}
          />
        ))}
      <p className="hint" style={{ margin: shown.length > 0 ? "14px 0 0" : "0" }}>
        {findings.length > shown.length && <>{findings.length - shown.length} more papers. </>}
        {playbooks > 0 ? `${pluralise(playbooks, "paper")} on management. ` : ""}
        <a href={`#/species/${encodeURIComponent(name)}`}>Full species page</a>
      </p>
    </>
  );
}

/**
 * One invasive species in one place, as a row that opens into a card: a photo with its credit,
 * how often it was recorded there, and what peer-reviewed papers report about its effect on the
 * local environment. The bar compares it with the most recorded species in the same list.
 */
export function SpeciesRow({
  species,
  max,
  lookup,
  where,
  open = false,
}: {
  species: HotspotSpecies;
  max: number;
  lookup: SpeciesLookup;
  where: string;
  open?: boolean;
}) {
  const photo = lookup.photoOf(species.name);
  const display = species.common_name ?? species.name;
  const source = safeUrl(photo?.photo_source_url);
  const hasPhoto = safeUrl(photo?.photo_url) != null;
  const findings = lookup.findingsOf(species.name);
  return (
    <details className="species-row" open={open}>
      <summary>
        <Photo photo={photo} display={display} ratio="thumb" />
        <span className="names">
          <strong>{species.common_name ?? <em>{species.name}</em>}</strong>
          {species.common_name && <em className="muted">{species.name}</em>}
          <span className="bar-track" aria-hidden="true">
            <span className="bar-fill" style={{ width: `${Math.max(2, (species.records / Math.max(1, max)) * 100)}%` }} />
          </span>
        </span>
        <span className="count">
          <strong>{species.records.toLocaleString("en-US")}</strong>
          <span className="hint">{yearSpan(species.first_year, species.last_year)}</span>
        </span>
      </summary>
      <div className="species-body">
        <Photo photo={photo} display={display} />
        {hasPhoto && photo?.photo_credit && (
          <div className="credit">
            {photo.photo_credit}
            {source && (
              <>
                {" "}
                <a href={source} target="_blank" rel="noopener noreferrer">
                  Photo page
                </a>
              </>
            )}
          </div>
        )}
        <p className="muted" style={{ margin: "10px 0 0" }}>
          {pluralise(species.records, "record")} {where}, {yearSpan(species.first_year, species.last_year)}.
        </p>
        <Research findings={findings} playbooks={lookup.playbooksOf(species.name)} name={species.name} />
      </div>
    </details>
  );
}

/** A ranked list of species, the most recorded first, the first one open. */
export function SpeciesList({
  species,
  lookup,
  where,
  limit = 12,
  scope,
}: {
  species: HotspotSpecies[];
  lookup: SpeciesLookup;
  where: string;
  limit?: number;
  /** Changes when the region changes, so the rows start fresh (the first one open). */
  scope: string;
}) {
  const max = species[0]?.records ?? 1;
  return (
    <div className="species-list">
      {species.slice(0, limit).map((s, i) => (
        <SpeciesRow key={`${scope}|${s.name}`} species={s} max={max} lookup={lookup} where={where} open={i === 0} />
      ))}
      {species.length > limit && (
        <p className="hint" style={{ margin: "8px 0 0" }}>
          And {pluralise(species.length - limit, "more species")}. Narrow the region or pick a species above to see them.
        </p>
      )}
    </div>
  );
}
