import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { Feature, Geometry } from "geojson";
import type { HotspotCell, ZoneProps } from "../api/types";
import { HEAT_OPACITY, cellKey, heatLevel, type Bounds } from "../lib/hotspots";
import { token, useResolvedTheme } from "../lib/theme";

const OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export interface HotspotMapProps {
  zone: Feature<Geometry, ZoneProps> | null;
  cells: HotspotCell[];
  selected: string | null;
  onSelect: (key: string | null) => void;
  /** Called with [west, south, east, north] whenever the visible area changes. */
  onView?: (view: Bounds) => void;
  /** Changing this number fits the map to the park again. */
  fitKey?: number;
  label: string;
}

/**
 * Squares shaded by how many invasive records fall in them, over a greyscale map. Shade carries
 * the count; a ranked list beside the map offers every square to keyboard and screen-reader
 * users, since map shapes cannot take focus.
 */
export function HotspotMap({ zone, cells, selected, onSelect, onView, fitKey = 0, label }: HotspotMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const zoneLayer = useRef<L.GeoJSON | null>(null);
  const cellLayer = useRef<L.LayerGroup | null>(null);
  const selectedBounds = useRef<L.LatLngBounds | null>(null);
  const theme = useResolvedTheme();
  // The latest callbacks, so the map's own event handlers never act on stale ones.
  const viewCb = useRef(onView);
  const selectCb = useRef(onSelect);
  viewCb.current = onView;
  selectCb.current = onSelect;

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current).setView([20, 0], 2); // SVG: no deferred canvas redraw to outlive the map
    m.on("moveend", () => {
      if (map.current !== m) return; // the map was removed while this event was queued
      const b = m.getBounds();
      viewCb.current?.([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
    });
    m.on("click", () => selectCb.current(null)); // a click on empty ground clears the selection
    // The map sits in a layout that changes size (filters wrapping, the window resizing).
    const watch = new ResizeObserver(() => m.invalidateSize());
    watch.observe(el.current);
    L.tileLayer(OSM, {
      maxZoom: 18,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    cellLayer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => {
      watch.disconnect();
      m.off();
      m.stop();
      m.remove();
      map.current = null;
      zoneLayer.current = null;
      cellLayer.current = null;
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
  }, [zone, theme, fitKey]);

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
        bubblingMouseEvents: false, // a click on a square is not a click on the empty map
      });
      rect.bindTooltip(`${c.records} ${c.records === 1 ? "record" : "records"}, ${c.species_count} species`);
      rect.on("click", () => selectCb.current(isSelected ? null : key));
      group.addLayer(rect);
    }
  }, [cells, selected, theme]);

  // Move to a square when it is chosen from the list or the map.
  useEffect(() => {
    const m = map.current;
    const b = selectedBounds.current;
    if (m && b && selected) m.fitBounds(b.pad(4), { maxZoom: 14, animate: false });
  }, [selected]);

  return <div ref={el} className="map" role="region" aria-label={label} />;
}
