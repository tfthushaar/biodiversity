import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { Feature, Geometry } from "geojson";
import type { HotspotCell, RecordsGeoJSON, ZoneProps } from "../api/types";
import { HEAT_OPACITY, cellKey, heatLevel } from "../lib/hotspots";
import { token, useResolvedTheme } from "../lib/theme";

const OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export interface HotspotMapProps {
  zone: Feature<Geometry, ZoneProps> | null;
  cells: HotspotCell[];
  selected: string | null;
  onSelect: (key: string | null) => void;
  /** Individual invasive records, drawn as small dots under the squares. */
  points: RecordsGeoJSON | null;
  label: string;
}

/**
 * Squares shaded by how many invasive records fall in them, over a greyscale map. Shade carries
 * the count; a ranked list beside the map offers every square to keyboard and screen-reader
 * users, since map shapes cannot take focus.
 */
export function HotspotMap({ zone, cells, selected, onSelect, points, label }: HotspotMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const zoneLayer = useRef<L.GeoJSON | null>(null);
  const cellLayer = useRef<L.LayerGroup | null>(null);
  const pointLayer = useRef<L.LayerGroup | null>(null);
  const selectedBounds = useRef<L.LatLngBounds | null>(null);
  const theme = useResolvedTheme();

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { preferCanvas: true }).setView([20, 0], 2);
    L.tileLayer(OSM, {
      maxZoom: 18,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    pointLayer.current = L.layerGroup().addTo(m);
    cellLayer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  // The park's outline, and the view that fits it.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    zoneLayer.current?.remove();
    if (!zone) return;
    const layer = L.geoJSON(zone, {
      style: { color: token("--ink"), weight: 2, dashArray: "6 5", fill: false, interactive: false } as L.PathOptions,
    }).addTo(m);
    layer.bringToBack();
    zoneLayer.current = layer;
    const b = layer.getBounds();
    if (b.isValid()) m.fitBounds(b.pad(0.08), { animate: false });
  }, [zone, theme]);

  // The squares.
  useEffect(() => {
    const group = cellLayer.current;
    if (!group) return;
    group.clearLayers();
    selectedBounds.current = null;
    const max = Math.max(0, ...cells.map((c) => c.records));
    const hot = token("--hot").split(",").map((v) => v.trim()).join(",");
    const ink = token("--ink");
    for (const c of cells) {
      const key = cellKey(c);
      const isSelected = key === selected;
      const bounds = L.latLngBounds([c.south, c.west], [c.north, c.east]);
      if (isSelected) selectedBounds.current = bounds;
      const rect = L.rectangle(bounds, {
        color: ink,
        weight: isSelected ? 3 : 1,
        opacity: isSelected ? 1 : 0.4,
        fillColor: `rgb(${hot})`,
        fillOpacity: HEAT_OPACITY[heatLevel(c.records, max)],
      });
      rect.bindTooltip(`${c.records} ${c.records === 1 ? "record" : "records"}, ${c.species_count} species`);
      rect.on("click", () => onSelect(isSelected ? null : key));
      group.addLayer(rect);
    }
  }, [cells, selected, onSelect, theme]);

  // Move to a square when it is chosen from the list or the map.
  useEffect(() => {
    const m = map.current;
    const b = selectedBounds.current;
    if (m && b && selected) m.fitBounds(b.pad(4), { maxZoom: 14, animate: false });
  }, [selected]);

  // Individual records, quiet and small.
  useEffect(() => {
    const group = pointLayer.current;
    if (!group) return;
    group.clearLayers();
    if (!points) return;
    const ink = token("--ink");
    for (const f of points.features) {
      const [lon, lat] = f.geometry.coordinates;
      if (lon == null || lat == null) continue;
      group.addLayer(
        L.circleMarker([lat, lon], { radius: 2.5, stroke: false, fillColor: ink, fillOpacity: 0.7 }).bindTooltip(
          f.properties.species,
        ),
      );
    }
  }, [points, theme]);

  return <div ref={el} className="map" role="region" aria-label={label} />;
}
