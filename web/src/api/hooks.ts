import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { rest } from "./rest";
import type {
  Alert,
  Finding,
  HotspotResult,
  ModelVersion,
  Playbook,
  SourceHealth,
  SpeciesPhoto,
  SpeciesProfile,
  YearCount,
  ZoneReportRow,
  ZonesGeoJSON,
} from "./types";

// Data changes when a worker runs (every few hours), so a short cache is plenty and keeps the
// dashboard quick without ever showing anything stale for long.
const STALE = 5 * 60 * 1000;

const q = <T>(key: unknown[], path: string) =>
  ({
    queryKey: key,
    queryFn: ({ signal }: { signal: AbortSignal }) => rest<T>(path, signal),
    staleTime: STALE,
    placeholderData: keepPreviousData, // refetch keeps the frame: no skeleton flash
  }) as const;

export const useZones = () => useQuery(q<ZonesGeoJSON>(["zones"], "/rpc/zones_geojson"));

/** What narrows the squares on the map. Every field is optional. */
export interface HotspotFilters {
  /** Source names; none means every source. */
  sources?: string[];
  yearFrom?: number | null;
  yearTo?: number | null;
  kingdom?: string | null;
  /** One species, by scientific name. The database counts it exactly. */
  species?: string | null;
}

/** Invasive records grouped into squares `km` kilometres across, with the species in each. */
export const useHotspots = (zone: string | null, km: number, f: HotspotFilters = {}, enabled = true) => {
  const params = new URLSearchParams({ p_zone: zone ?? "", p_km: String(km) });
  if (f.sources?.length) params.set("p_sources", f.sources.join(","));
  if (f.yearFrom != null) params.set("p_year_from", String(f.yearFrom));
  if (f.yearTo != null) params.set("p_year_to", String(f.yearTo));
  if (f.kingdom) params.set("p_kingdom", f.kingdom);
  if (f.species) params.set("p_species", f.species);
  return useQuery({
    ...q<HotspotResult>(
      ["hotspots", zone, km, f.sources ?? [], f.yearFrom ?? null, f.yearTo ?? null, f.kingdom ?? null, f.species ?? null],
      // %20 for a space, as every other request here writes it, in place of the form-style +.
      `/rpc/hotspot_grid?${params.toString().replace(/\+/g, "%20")}`,
    ),
    enabled: zone !== null && enabled,
  });
};

/** Invasive records per year, for one park or all of them. */
export const useInvasiveByYear = (zone: string | null) =>
  useQuery(q<YearCount[]>(["by-year", zone], `/rpc/invasive_by_year${zone ? `?p_zone=${encodeURIComponent(zone)}` : ""}`));

/** One species' records by park, year and source. */
export const useSpeciesProfile = (name: string | null) =>
  useQuery({
    ...q<SpeciesProfile>(["species-profile", name], `/rpc/species_profile?p_species=${encodeURIComponent(name ?? "")}`),
    enabled: name !== null,
  });

export const useSpeciesPhotos = () =>
  useQuery(
    q<SpeciesPhoto[]>(
      ["species-photos"],
      "/species?select=scientific_name,common_name,photo_url,photo_credit,photo_license,photo_source_url&photo_url=not.is.null&limit=1000",
    ),
  );

export const useReports = () =>
  useQuery(
    q<ZoneReportRow[]>(
      ["reports"],
      "/zone_reports?select=computed_at,report,zones(slug,name)&order=zone_id",
    ),
  );

export const useAlerts = () =>
  useQuery(
    q<Alert[]>(
      ["alerts"],
      "/alerts?select=id,kind,severity,created_at,window_start,evidence,zones(slug,name),species(scientific_name,common_name)&order=created_at.desc&limit=100",
    ),
  );

export const useFindings = () =>
  useQuery(
    q<Finding[]>(
      ["findings"],
      "/impact_findings?select=id,finding_type,affected,summary,certainty,region_note,source_quotes,citation_text,citation_url,citation_doi,citation_year,citation_journal,verified_on,species:species!invasive_species_id(scientific_name,common_name),zones(slug,name)&order=id",
    ),
  );

export const usePlaybooks = () =>
  useQuery(
    q<Playbook[]>(
      ["playbooks"],
      "/mitigation_playbooks?select=id,method,description,study_design,region_note,source_quotes,citation_text,citation_url,citation_doi,citation_year,citation_journal,verified_on,species(scientific_name,common_name)&order=id",
    ),
  );

export const useModels = () =>
  useQuery(q<ModelVersion[]>(["models"], "/model_versions?select=id,name,task,weights_uri,metrics&order=id"));

export const useSources = () => useQuery(q<SourceHealth[]>(["sources"], "/source_health?order=id"));

/** Species GRIIS lists as purely alien and invasive in India: the ones the dossier can be about. */
