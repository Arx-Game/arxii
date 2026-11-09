/**
 * What the region map shows (#5030): one of four views, anchored on the selected domain at
 * any tier, and the names that fit at the current zoom. Pure, so the page can be tested
 * without a canvas. The owner's words for the views are the picker's copy; the anchor is
 * whatever domain is selected (or being carved), and with none a realm's roots stand in.
 */
import type { RegionMapFootprint } from '../types';
import { centroid } from './regionMapCanvas';

export type MapView = 'geography' | 'domain' | 'domain-vassal' | 'all';

export const MAP_VIEWS: readonly MapView[] = ['geography', 'domain', 'domain-vassal', 'all'];

export const MAP_VIEW_LABELS: Record<MapView, string> = {
  geography: 'Geography',
  domain: 'Domain',
  'domain-vassal': 'Domain-Vassal',
  all: 'All',
};

export const DEFAULT_MAP_VIEW: MapView = 'all';

/** A placed name on the names layer, in screen pixels, centred on (x, y). */
export interface Label {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  areaId: number;
}

export const LABEL_PX = 12;
const LABEL_PAD_PX = 8;

export function isMapView(value: unknown): value is MapView {
  return typeof value === 'string' && (MAP_VIEWS as readonly string[]).includes(value);
}

/** The footprints of `realmId` (every realm when null) whose parent is not on the map. */
export function rootsOf(
  footprints: RegionMapFootprint[],
  realmId: number | null
): RegionMapFootprint[] {
  const present = new Set(footprints.map((f) => f.area_id));
  return footprints.filter(
    (f) =>
      (realmId == null || f.realm_id === realmId) &&
      (f.parent_id == null || !present.has(f.parent_id))
  );
}

function childrenByParent(footprints: RegionMapFootprint[]): Map<number, RegionMapFootprint[]> {
  const out = new Map<number, RegionMapFootprint[]>();
  for (const f of footprints) {
    if (f.parent_id == null) continue;
    const list = out.get(f.parent_id);
    if (list) list.push(f);
    else out.set(f.parent_id, [f]);
  }
  return out;
}

/** The anchors and everything beneath them on the ladder, every tier down. */
function withDescendants(
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[]
): RegionMapFootprint[] {
  const children = childrenByParent(footprints);
  const seen = new Set<number>();
  const out: RegionMapFootprint[] = [];
  const frontier = [...anchors];
  while (frontier.length > 0) {
    const f = frontier.pop()!;
    if (seen.has(f.area_id)) continue;
    seen.add(f.area_id);
    out.push(f);
    frontier.push(...(children.get(f.area_id) ?? []));
  }
  return out;
}

/** What a view draws: nothing, the anchors, their whole ladders, or everything. */
export function visibleFootprints(
  view: MapView,
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[]
): RegionMapFootprint[] {
  switch (view) {
    case 'geography':
      return [];
    case 'domain':
      return anchors;
    case 'domain-vassal':
      return withDescendants(footprints, anchors);
    case 'all':
      return footprints;
  }
}

function overlaps(a: Label, b: Label): boolean {
  return Math.abs(a.x - b.x) * 2 < a.w + b.w && Math.abs(a.y - b.y) * 2 < a.h + b.h;
}

function fitsWidth(
  pips: RegionMapFootprint['pips'],
  width: number,
  project: (x: number, y: number) => [number, number]
): boolean {
  let minX = Infinity;
  let maxX = -Infinity;
  for (const [x] of pips) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
  }
  const [left] = project(minX - 0.5, 0);
  const [right] = project(maxX + 0.5, 0);
  return right - left >= width;
}

/**
 * The names a view draws, placed in screen space. Domain names the anchors wherever they
 * are; Domain-Vassal names the anchors' direct children always and the deeper tiers where
 * they fit, never the anchor itself (its name is the panel's heading and would sit inside a
 * child's); All names what fits. "Fits": the footprint's projected width carries the name,
 * and the name's box crosses no name already placed. Top tiers place first, so a parent's
 * name wins over a child's. `project` maps a pip centre to the screen; `measure` is the
 * text width at `LABEL_PX`.
 */
export function placeNames(
  view: MapView,
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[],
  project: (x: number, y: number) => [number, number],
  measure: (text: string) => number
): Label[] {
  if (view === 'geography') return [];
  const anchorIds = new Set(anchors.map((a) => a.area_id));
  const visible = visibleFootprints(view, footprints, anchors);
  const candidates =
    view === 'domain-vassal' ? visible.filter((f) => !anchorIds.has(f.area_id)) : visible;
  const exempt = new Set<number>();
  if (view === 'domain') for (const a of anchors) exempt.add(a.area_id);
  if (view === 'domain-vassal') {
    for (const f of candidates)
      if (f.parent_id != null && anchorIds.has(f.parent_id)) exempt.add(f.area_id);
  }
  const ordered = [...candidates].sort((a, b) => b.level - a.level || a.area_id - b.area_id);
  const placed: Label[] = [];
  for (const f of ordered) {
    if (!f.name || f.pips.length === 0) continue;
    const w = measure(f.name) + LABEL_PAD_PX;
    const h = LABEL_PX + 4;
    if (!exempt.has(f.area_id) && !fitsWidth(f.pips, w, project)) continue;
    const [cx, cy] = centroid(f.pips);
    const [x, y] = project(cx, cy);
    const label: Label = { text: f.name, x, y, w, h, areaId: f.area_id };
    if (placed.some((p) => overlaps(p, label))) continue;
    placed.push(label);
  }
  return placed;
}
