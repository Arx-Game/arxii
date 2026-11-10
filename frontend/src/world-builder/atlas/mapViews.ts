/**
 * What the region map shows (#5030): one of four views, anchored on the selected domain at
 * any tier, and the names that fit at the current zoom. Pure, so the page can be tested
 * without a canvas. The owner's words for the views are the picker's copy; the anchor is
 * whatever domain is selected (or being carved), and with none a realm's roots stand in.
 * Domain is the anchor and the tier below it, each child with a border line, since the
 * lines between a duchy's counties are what the owner reads the map for (#5056);
 * Domain-Vassal borders every tier beneath, lighter as it goes down.
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

/** The anchors and the tier directly beneath each. */
function withChildren(
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[]
): RegionMapFootprint[] {
  const children = childrenByParent(footprints);
  const seen = new Set<number>();
  const out: RegionMapFootprint[] = [];
  for (const anchor of anchors) {
    for (const f of [anchor, ...(children.get(anchor.area_id) ?? [])]) {
      if (seen.has(f.area_id)) continue;
      seen.add(f.area_id);
      out.push(f);
    }
  }
  return out;
}

/** What a view draws: nothing, the anchors with the tier below, their whole ladders, or everything. */
export function visibleFootprints(
  view: MapView,
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[]
): RegionMapFootprint[] {
  switch (view) {
    case 'geography':
      return [];
    case 'domain':
      return withChildren(footprints, anchors);
    case 'domain-vassal':
      return withDescendants(footprints, anchors);
    case 'all':
      return footprints;
  }
}

/** Border line widths by depth beneath the anchor: its children, their children, and deeper. */
export const BORDER_WIDTHS = [2, 1, 0.5] as const;

/**
 * The border each visible footprint beneath an anchor draws, by area id (#5056): in Domain
 * the tier below the anchor at full width; in Domain-Vassal every tier beneath, one step
 * lighter per tier so a county line never reads as a duchy line. Geography and All draw no
 * borders; the selected or carved outline is the page's own and is not here.
 */
export function borderWidths(
  view: MapView,
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[]
): Map<number, number> {
  const out = new Map<number, number>();
  if (view !== 'domain' && view !== 'domain-vassal') return out;
  const children = childrenByParent(footprints);
  const deepest = view === 'domain' ? 1 : Infinity;
  const frontier: [RegionMapFootprint, number][] = anchors.map((a) => [a, 0]);
  while (frontier.length > 0) {
    const [f, depth] = frontier.pop()!;
    if (depth > 0 && !out.has(f.area_id)) {
      out.set(f.area_id, BORDER_WIDTHS[Math.min(depth, BORDER_WIDTHS.length) - 1]);
    }
    if (depth >= deepest) continue;
    for (const child of children.get(f.area_id) ?? []) frontier.push([child, depth + 1]);
  }
  return out;
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
 * The names a view draws, placed in screen space. Domain and Domain-Vassal name the anchors'
 * direct children always, never an anchor that has children (its name is the panel's heading
 * and would sit inside a child's); an anchor with nothing beneath it is named itself in
 * Domain; Domain-Vassal names the deeper tiers where they fit; All names what fits. "Fits": the footprint's projected width carries the name,
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
  const anchored = view === 'domain' || view === 'domain-vassal';
  const withChild = new Set(
    anchored
      ? visible
          .filter((f) => f.parent_id != null && anchorIds.has(f.parent_id))
          .map((f) => f.parent_id!)
      : []
  );
  const candidates = anchored
    ? visible.filter(
        (f) => !anchorIds.has(f.area_id) || (view === 'domain' && !withChild.has(f.area_id))
      )
    : visible;
  // named whatever their size: the tier below an anchor, and a childless anchor in Domain
  const exempt = new Set<number>();
  if (anchored) {
    for (const f of candidates) {
      if (anchorIds.has(f.area_id) || (f.parent_id != null && anchorIds.has(f.parent_id))) {
        exempt.add(f.area_id);
      }
    }
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
