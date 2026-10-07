import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { rest } from "./rest";
import type {
  Alert,
  Finding,
  InvasiveSpecies,
  ModelVersion,
  Playbook,
  RecordsGeoJSON,
  SourceHealth,
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

export const useRecords = (zone: string | null) =>
  useQuery(
    q<RecordsGeoJSON>(
      ["records", zone],
      `/rpc/records_geojson?p_kind=all&p_limit=5000${zone ? `&p_zone=${encodeURIComponent(zone)}` : ""}`,
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
      "/impact_findings?select=id,finding_type,affected,summary,certainty,region_note,source_quotes,citation_text,citation_url,verified_on,species:species!invasive_species_id(scientific_name,common_name),zones(slug,name)&order=id",
    ),
  );

export const usePlaybooks = () =>
  useQuery(
    q<Playbook[]>(
      ["playbooks"],
      "/mitigation_playbooks?select=id,method,description,effectiveness,evidence_strength,cost_tier,risks,failure_cases,region_note,source_quotes,citation_text,citation_url,verified_on,species(scientific_name,common_name)&order=id",
    ),
  );

export const useModels = () =>
  useQuery(q<ModelVersion[]>(["models"], "/model_versions?select=id,name,task,weights_uri,metrics&order=id"));

export const useSources = () => useQuery(q<SourceHealth[]>(["sources"], "/source_health?order=id"));

/** Species GRIIS lists as purely alien and invasive in India: the ones the dossier can be about. */
export const useInvasiveSpecies = () =>
  useQuery(
    q<InvasiveSpecies[]>(
      ["invasive-species"],
      "/invasive_status?select=species_id,establishment_means,species(scientific_name,common_name,kingdom)&country=eq.IN&is_invasive=eq.true&origin_class=eq.alien&limit=1000",
    ),
  );
