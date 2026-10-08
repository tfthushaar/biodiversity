import type { Finding, HotspotSpecies, SpeciesPhoto } from "../api/types";
import { pluralise } from "../lib/format";
import { yearSpan } from "../lib/hotspots";
import { FindingCard } from "./cards";
import { safeUrl } from "./evidence";

/**
 * One invasive species in one place: a photo with its credit, how often it was recorded there,
 * and what cited research reports about its effect on the local environment.
 */
export function SpeciesCard({
  species,
  photo,
  findings,
  playbooks,
  where,
}: {
  species: HotspotSpecies;
  photo: SpeciesPhoto | undefined;
  findings: Finding[];
  playbooks: number;
  where: string;
}) {
  const shown = findings.slice(0, 2);
  const image = safeUrl(photo?.photo_url);
  const source = safeUrl(photo?.photo_source_url);
  const display = species.common_name ?? species.name;
  return (
    <article className="card species-card" aria-label={display}>
      <div className="photo">
        {image ? (
          <img src={image} alt={`Photograph of ${display}`} loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <div className="none">No openly licensed photo available</div>
        )}
      </div>
      {image && photo?.photo_credit && (
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
      <div className="body">
        <h3>{species.common_name ?? <em>{species.name}</em>}</h3>
        {species.common_name && (
          <div className="muted">
            <em>{species.name}</em>
          </div>
        )}
        <div className="facts">
          <span className="badge invasive">
            {pluralise(species.records, "record")} {where}
          </span>
          <span className="badge">{yearSpan(species.first_year, species.last_year)}</span>
        </div>

        <h4>Effect on the local environment</h4>
        {shown.length === 0 ? (
          <p className="hint" style={{ margin: 0 }}>
            No cited research on this species' effects is on file yet.
          </p>
        ) : (
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
          ))
        )}

        <p className="hint" style={{ margin: "14px 0 0" }}>
          {findings.length > shown.length && <>{findings.length - shown.length} more cited findings. </>}
          {playbooks > 0 ? `${pluralise(playbooks, "cited management option")}. ` : ""}
          <a href={`#/species/${encodeURIComponent(species.name)}`}>Full species page</a>
        </p>
      </div>
    </article>
  );
}
