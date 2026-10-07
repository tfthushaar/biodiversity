import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { RecordClass, RecordsGeoJSON, ZonesGeoJSON } from "../api/types";
import { fmtDate } from "../lib/format";
import { token, useResolvedTheme } from "../lib/theme";
import { safeUrl } from "./evidence";

export interface MapProps {
  zones: ZonesGeoJSON;
  records: RecordsGeoJSON;
  selected: string | null;
  show: Record<RecordClass, boolean>;
}

const OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

/** Text from the database goes into the popup as DOM text, never as HTML. */
function popup(p: RecordsGeoJSON["features"][number]["properties"]): HTMLElement {
  const box = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = p.species;
  box.append(title);
  const line = (text: string) => {
    const d = document.createElement("div");
    d.textContent = text;
    box.append(d);
  };
  if (p.common_name) line(p.common_name);
  line(`${fmtDate(p.captured_at)} · ${p.zone} · ${p.class}`);
  const href = safeUrl(p.url);
  if (href) {
    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "Open the record";
    box.append(a);
  }
  return box;
}

export function MapView({ zones, records, selected, show }: MapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const zoneLayer = useRef<L.GeoJSON | null>(null);
  const pointLayer = useRef<L.LayerGroup | null>(null);
  const theme = useResolvedTheme();

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { preferCanvas: true, worldCopyJump: true }).setView([11.8, 76.5], 8);
    L.tileLayer(OSM, {
      maxZoom: 18,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    map.current = m;
    pointLayer.current = L.layerGroup().addTo(m);
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  // Zone boundaries.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    zoneLayer.current?.remove();
    const ink = token("--ink-2");
    const layer = L.geoJSON(zones, {
      style: (f) => ({
        color: ink,
        weight: f?.properties?.slug === selected ? 3 : 1.5,
        fillColor: token("--series-1"),
        fillOpacity: f?.properties?.slug === selected ? 0.1 : 0.04,
      }),
      onEachFeature: (f, l) => l.bindTooltip(String(f.properties?.name ?? ""), { sticky: true }),
    }).addTo(m);
    zoneLayer.current = layer;
    layer.bringToBack();
    const target = selected
      ? L.geoJSON(zones, { filter: (f) => f.properties?.slug === selected }).getBounds()
      : layer.getBounds();
    if (target.isValid()) m.fitBounds(target.pad(0.1), { animate: false });
  }, [zones, selected, theme]);

  // Sightings. Context (native, introduced) is drawn small and quiet underneath; invasives are
  // the point of the map, so they are larger, on top, and carry a surface ring to stay legible
  // where they overlap. Each invasive point has a generous invisible hit area.
  useEffect(() => {
    const group = pointLayer.current;
    if (!group) return;
    group.clearLayers();
    const colour: Record<RecordClass, string> = {
      native: token("--native"),
      introduced: token("--introduced"),
      invasive: token("--invasive"),
    };
    const ring = token("--surface");
    const order: RecordClass[] = ["native", "introduced", "invasive"];
    for (const cls of order) {
      if (!show[cls]) continue;
      for (const f of records.features) {
        if (f.properties.class !== cls) continue;
        const [lon, lat] = f.geometry.coordinates;
        if (lon == null || lat == null) continue;
        if (cls === "invasive") {
          const halo = L.circleMarker([lat, lon], { radius: 14, stroke: false, fillOpacity: 0, interactive: true });
          halo.bindPopup(() => popup(f.properties));
          halo.bindTooltip(f.properties.species);
          group.addLayer(halo);
          group.addLayer(
            L.circleMarker([lat, lon], {
              radius: 6, color: ring, weight: 2, fillColor: colour.invasive, fillOpacity: 1, interactive: false,
            }),
          );
        } else {
          group.addLayer(
            L.circleMarker([lat, lon], {
              radius: 3, stroke: false, fillColor: colour[cls], fillOpacity: 0.45, interactive: false,
            }),
          );
        }
      }
    }
  }, [records, show, theme]);

  return <div ref={el} className="map" role="region" aria-label="Map of recorded sightings" />;
}
