import type { Feature, FeatureCollection, Geometry, Point } from "geojson";

export interface ZoneProps {
  slug: string;
  name: string;
  group: string | null;
  country: string;
  observations: number;
  species: number;
  invasive_records: number;
  invasive_species: number;
}
export type ZonesGeoJSON = FeatureCollection<Geometry, ZoneProps>;

/** One species recorded in a hotspot cell. */
export interface HotspotSpecies {
  name: string;
  common_name: string | null;
  records: number;
  first_year: number;
  last_year: number;
}

/** A square of the map, in degrees, and the invasive records inside it. */
export interface HotspotCell {
  west: number;
  south: number;
  east: number;
  north: number;
  records: number;
  species_count: number;
  species: HotspotSpecies[];
}

export interface HotspotResult {
  cell: number;
  cells: HotspotCell[];
}

/** A species' representative photo, with the credit and licence its owner chose. */
export interface SpeciesPhoto {
  scientific_name: string;
  common_name: string | null;
  photo_url: string | null;
  photo_credit: string | null;
  photo_license: string | null;
  photo_source_url: string | null;
}

/** What kind of record a point is. */
export type RecordClass = "invasive" | "introduced" | "native";
export interface RecordProps {
  species: string;
  common_name: string | null;
  zone: string;
  captured_at: string;
  origin: "observer" | "model";
  class: RecordClass;
  url: string | null;
}
export type RecordsGeoJSON = FeatureCollection<Point, RecordProps>;
export type RecordFeature = Feature<Point, RecordProps>;

export type Certainty =
  | "experimental"
  | "observational"
  | "review"
  | "preliminary"
  | "unverified_concern";

export interface SpeciesRef {
  scientific_name: string;
  common_name: string | null;
}

export interface Finding {
  id: number;
  finding_type: "impact" | "spread" | "concern";
  affected: string;
  summary: string;
  certainty: Certainty;
  region_note: string;
  source_quotes: string[];
  citation_text: string;
  citation_url: string;
  verified_on: string | null;
  species: SpeciesRef;
  zones: { slug: string; name: string } | null;
}

export interface Playbook {
  id: number;
  method: string;
  description: string;
  effectiveness: "low" | "moderate" | "high" | "variable" | null;
  evidence_strength: "low" | "moderate" | "high" | null;
  cost_tier: string | null;
  risks: string | null;
  failure_cases: string | null;
  region_note: string | null;
  source_quotes: string[];
  citation_text: string;
  citation_url: string | null;
  verified_on: string | null;
  species: SpeciesRef;
}

export interface Alert {
  id: number;
  kind: string;
  severity: "low" | "medium" | "high";
  created_at: string;
  window_start: string | null;
  evidence: { caveat?: string; records?: number; first_record?: string; species?: string } & Record<
    string,
    unknown
  >;
  zones: { slug: string; name: string } | null;
  species: SpeciesRef | null;
}

export interface LayerResult {
  layer: string;
  status: "ok" | "insufficient";
  reason: string | null;
  needs: string | null;
  caution: string | null;
  detail: Record<string, unknown>;
}

export interface ReportFinding {
  species: string;
  common_name: string | null;
  zone: string | null;
  finding_type: string;
  affected: string;
  summary: string;
  certainty: Certainty;
  region_note: string;
  quotes: string[];
  citation: string;
  url: string;
  verified_on: string | null;
  records_in_zone: number;
  recorded_in_zone: boolean;
}

export interface ZoneReport {
  zone: string;
  observations: number;
  species: number;
  invasive_species: {
    species: string;
    common_name: string | null;
    records: number;
    first_record: string;
    last_record: string;
    sources: number;
  }[];
  layers: {
    documented: { status: string; findings: ReportFinding[]; note: string };
    cooccurrence: LayerResult;
    trend: LayerResult;
  };
}

export interface ZoneReportRow {
  computed_at: string;
  report: ZoneReport;
  zones: { slug: string; name: string };
}

export interface TradeoffRow {
  threshold: number;
  answered: number;
  accuracy_when_answered: number | null;
  invasives_named?: { rate: number | null };
  non_target_called_invasive?: Record<string, { rate: number | null; count: number; of: number }>;
}

export interface Rate {
  count: number;
  of: number;
  rate: number | null;
  ci95: [number, number];
}

export interface ModelMetrics {
  // Classifiers
  classes?: string[];
  split?: string;
  chosen?: { threshold: number; temperature: number; C: number };
  test_photos?: number;
  test_top1_without_threshold?: number;
  majority_class_baseline?: number;
  answered?: number;
  accuracy_when_answered?: number;
  dangerous_errors?: Rate;
  dangerous_errors_by_kind?: Record<string, Rate>;
  invasives_correctly_named?: Rate;
  same_cameras_top1?: number;
  new_cameras_top1?: number;
  threshold_tradeoff_on_test?: TradeoffRow[];
  caveats?: string[];
  // Detector
  dataset?: string;
  images?: number;
  "animal_image_level_at_0.2"?: Record<string, number | null>;
  image_level_by_threshold?: {
    threshold: number;
    precision: number | null;
    recall: number | null;
    false_alarm_rate: number | null;
  }[];
  caveat?: string;
}

export interface ModelVersion {
  id: number;
  name: string;
  task: "detector" | "plant_classifier" | "animal_classifier";
  weights_uri: string | null;
  metrics: ModelMetrics;
}

export interface SourceHealth {
  id: number;
  name: string;
  kind: string;
  license: string | null;
  attribution: string | null;
  base_url: string | null;
  last_run: string | null;
  fetched: number | null;
  skipped_dupe: number | null;
  failed: number | null;
  rejected: Record<string, number> | null;
  items: number;
}

/** How full the free-tier database is. */
export interface StorageStatus {
  db_bytes: number;
  budget_bytes: number;
}

export interface InvasiveSpecies {
  species_id: number;
  establishment_means: string | null;
  species: SpeciesRef & { kingdom: string | null };
}
