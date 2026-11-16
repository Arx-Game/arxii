/**
 * What the region map shows (#5030): one of four views, anchored on the selected domain at
 * any tier, and the names that fit at the current zoom. Pure, so the page can be tested
 * without a canvas. The owner's words for the views are the picker's copy; the anchor is
 * whatever domain is selected (or being carved), and with none a realm's roots stand in.
 * Domain is the anchor and the tier below it, each child with a border line, since the
 * lines between a duchy's counties are what the owner reads the map for (#5056);
 * Domain-Vassal borders every tier beneath, lighter as it goes down. Beneath the view sit
 * four tier toggles (#5157): a tier that is off draws no border, name or seat marker, and
 * its fill and click-to-select are untouched.
 */
import type { RegionMapFootprint } from '../types';
import { centroid, pipKey } from './regionMapCanvas';

export type MapView = 'geography' | 'domain' | 'domain-vassal' | 'all';

export const MAP_VIEWS: readonly MapView[] = ['geography', 'domain', 'domain-vassal', 'all'];

export const MAP_VIEW_LABELS: Record<MapView, string> = {
  geography: 'Geography',
  domain: 'Domain',
  'domain-vassal': 'Domain-Vassal',
  all: 'All',
};

export const DEFAULT_MAP_VIEW: MapView = 'all';

/** The tiers the map can draw or leave out (#5157), top first. */
export type MapTier = 'kingdom' | 'duchy' | 'county' | 'barony';

export const MAP_TIERS: readonly MapTier[] = ['kingdom', 'duchy', 'county', 'barony'];

export const MAP_TIER_LABELS: Record<MapTier, string> = {
  kingdom: 'Kingdom',
  duchy: 'Duchy',
  county: 'County',
  barony: 'Barony',
};

/** `AreaLevel` for each tier; a level outside these four is always drawn. */
const TIER_LEVELS: Record<MapTier, number> = { kingdom: 60, duchy: 56, county: 53, barony: 40 };

/** Barony starts off: 400 barony names at once would cover the map. */
export const DEFAULT_MAP_TIERS: readonly MapTier[] = ['kingdom', 'duchy', 'county'];

export type MapTiers = ReadonlySet<MapTier>;

export function isMapTier(value: unknown): value is MapTier {
  return typeof value === 'string' && (MAP_TIERS as readonly string[]).includes(value);
}

function tierOfLevel(level: number): MapTier | null {
  return MAP_TIERS.find((tier) => TIER_LEVELS[tier] === level) ?? null;
}

/**
 * A seat marker (#5157), at a pip: `rank` is 0 for a plain barony and one step up for each
 * of county, duchy and kingdom whose capital the pip is, among the tiers that are on.
 * `baronyId` and `name` are the barony standing there, when one does; an undefined barony
 * has no name to show.
 */
export interface SeatMarker {
  x: number;
  y: number;
  rank: number;
  baronyId: number | null;
  name: string;
}

/**
 * What an undefined rung's area is called (`almanach.UNDEFINED_AREA_NAME`). Nearly every
 * barony starts that way, so it is marked and never named: 400 of the same word say nothing.
 */
const UNDEFINED_NAME = 'Undefined';

/** Marker radius in screen pixels by `SeatMarker.rank`. */
export const SEAT_MARKER_PX = [3, 4.5, 6, 7.5] as const;

export function markerRadius(rank: number): number {
  return SEAT_MARKER_PX[Math.min(rank, SEAT_MARKER_PX.length - 1)];
}

function rankOfLevel(level: number): number {
  if (level >= TIER_LEVELS.kingdom) return 3;
  if (level >= TIER_LEVELS.duchy) return 2;
  if (level >= TIER_LEVELS.county) return 1;
  return 0;
}

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

/**
 * Whether a footprint's border, name and marker are drawn (#5157): its tier is on, or it is
 * what the selection asks for whatever the toggles say, which is the anchor itself and, in
 * the two Domain views, a selected county's own baronies.
 */
function drawsTier(
  f: RegionMapFootprint,
  tiers: MapTiers,
  view: MapView,
  anchorIds: Set<number>
): boolean {
  const tier = tierOfLevel(f.level);
  if (tier == null || tiers.has(tier)) return true;
  if (view !== 'domain' && view !== 'domain-vassal') return false;
  if (anchorIds.has(f.area_id)) return true;
  return tier === 'barony' && f.parent_id != null && anchorIds.has(f.parent_id);
}

/**
 * The seat markers a view draws (#5157), one per pip: every drawn footprint with a seat
 * marks it, and a pip that is the capital of several drawn tiers takes the highest.
 */
export function seatMarkers(
  view: MapView,
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[],
  tiers: MapTiers
): SeatMarker[] {
  if (view === 'geography') return [];
  const anchorIds = new Set(anchors.map((a) => a.area_id));
  const baronyAt = new Map<string, RegionMapFootprint>();
  for (const f of footprints) {
    if (f.level === TIER_LEVELS.barony && f.seat != null) {
      baronyAt.set(pipKey(f.seat[0], f.seat[1]), f);
    }
  }
  const out = new Map<string, SeatMarker>();
  for (const f of visibleFootprints(view, footprints, anchors)) {
    if (f.seat == null || !drawsTier(f, tiers, view, anchorIds)) continue;
    const key = pipKey(f.seat[0], f.seat[1]);
    const rank = rankOfLevel(f.level);
    const prior = out.get(key);
    if (prior && prior.rank >= rank) continue;
    const barony = baronyAt.get(key) ?? null;
    out.set(key, {
      x: f.seat[0],
      y: f.seat[1],
      rank,
      baronyId: barony?.area_id ?? null,
      name: barony && barony.name !== UNDEFINED_NAME ? barony.name : '',
    });
  }
  return [...out.values()];
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
  anchors: RegionMapFootprint[],
  tiers: MapTiers
): Map<number, number> {
  const out = new Map<number, number>();
  if (view !== 'domain' && view !== 'domain-vassal') return out;
  const anchorIds = new Set(anchors.map((a) => a.area_id));
  const children = childrenByParent(footprints);
  const deepest = view === 'domain' ? 1 : Infinity;
  const frontier: [RegionMapFootprint, number][] = anchors.map((a) => [a, 0]);
  while (frontier.length > 0) {
    const [f, depth] = frontier.pop()!;
    if (depth > 0 && !out.has(f.area_id) && drawsTier(f, tiers, view, anchorIds)) {
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
 * Domain; Domain-Vassal names the deeper tiers where they fit; All names what fits. "Fits":
 * the footprint's projected width carries the name, and the name's box crosses no name
 * already placed. Top tiers place first, so a parent's name wins over a child's.
 *
 * A barony is one pip, so it is never wide enough; its name sits under its marker instead
 * (#5157), or over it or beside it when that place is taken, whenever the barony is drawn. A capital is named the same way whatever the Barony
 * toggle says, while its domain is named or is the anchor, so Domain on a duchy names the
 * duchy's capital and each county's and no other barony, and All at a distance names none.
 * A capital's name places after the domain names of its tier and before plain baronies.
 * `project` maps a pip centre to the screen; `measure` is the text width at `LABEL_PX`.
 */
export function placeNames(
  view: MapView,
  footprints: RegionMapFootprint[],
  anchors: RegionMapFootprint[],
  project: (x: number, y: number) => [number, number],
  measure: (text: string) => number,
  tiers: MapTiers
): Label[] {
  if (view === 'geography') return [];
  const anchorIds = new Set(anchors.map((a) => a.area_id));
  const visible = visibleFootprints(view, footprints, anchors);
  const anchored = view === 'domain' || view === 'domain-vassal';
  const drawn = visible.filter((f) => drawsTier(f, tiers, view, anchorIds));
  const withChild = new Set(
    anchored
      ? visible
          .filter((f) => f.parent_id != null && anchorIds.has(f.parent_id))
          .map((f) => f.parent_id!)
      : []
  );
  // named whatever their size: the tier below an anchor, and a childless anchor in Domain
  const exempt = (f: RegionMapFootprint) =>
    anchored && (anchorIds.has(f.area_id) || (f.parent_id != null && anchorIds.has(f.parent_id)));
  const h = LABEL_PX + 4;
  const boxOf = (text: string) => measure(text) + LABEL_PAD_PX;
  const markers = new Map(
    seatMarkers(view, footprints, anchors, tiers).map((m) => [pipKey(m.x, m.y), m] as const)
  );
  // where a marker's name may sit, best first: under it, over it, to either side, a row out
  const byMarker = (marker: SeatMarker): Label[] => {
    if (!marker.name || marker.baronyId == null) return [];
    const [x, y] = project(marker.x, marker.y);
    const w = boxOf(marker.name);
    const r = markerRadius(marker.rank);
    const at = (lx: number, ly: number): Label => ({
      text: marker.name,
      x: lx,
      y: ly,
      w,
      h,
      areaId: marker.baronyId!,
    });
    return [
      at(x, y + r + h / 2),
      at(x, y - r - h / 2),
      at(x + r + w / 2, y),
      at(x - r - w / 2, y),
      // a capital at its domain's centre sits under the domain's own name: one row further
      at(x, y + r + h * 1.5),
      at(x, y - r - h * 1.5),
    ];
  };

  // [level, 0 for a domain's own name or 1 for a marker's, area id, the places it may sit]
  const entries: [number, number, number, Label[]][] = [];
  const namedPips = new Set<string>();
  const byTier = [...drawn].sort((a, b) => b.level - a.level || a.area_id - b.area_id);
  for (const f of byTier) {
    const marker = f.seat ? markers.get(pipKey(f.seat[0], f.seat[1])) : undefined;
    const markerKey = marker ? pipKey(marker.x, marker.y) : '';
    const nameMarker = () => {
      const spots = marker ? byMarker(marker) : [];
      if (spots.length === 0 || namedPips.has(markerKey)) return;
      namedPips.add(markerKey);
      entries.push([f.level, 1, f.area_id, spots]);
    };
    if (f.level === TIER_LEVELS.barony) {
      nameMarker();
      continue;
    }
    if (!f.name || f.pips.length === 0) continue;
    const isAnchor = anchored && anchorIds.has(f.area_id);
    const fits = exempt(f) || fitsWidth(f.pips, boxOf(f.name), project);
    const ownName = !isAnchor || (view === 'domain' && !withChild.has(f.area_id));
    if (ownName && fits) {
      const [cx, cy] = centroid(f.pips);
      const [x, y] = project(cx, cy);
      const own = { text: f.name, x, y, w: boxOf(f.name), h, areaId: f.area_id };
      entries.push([f.level, 0, f.area_id, [own]]);
    }
    if (isAnchor || fits) nameMarker();
  }
  entries.sort((a, b) => b[0] - a[0] || a[1] - b[1] || a[2] - b[2]);
  const placed: Label[] = [];
  for (const [, , , spots] of entries) {
    const free = spots.find((spot) => !placed.some((p) => overlaps(p, spot)));
    if (free) placed.push(free);
  }
  return placed;
}

/**
 * The footprints under an open regional event (#5080): the struck area and everything
 * beneath it on the ladder, walked through `parent_id` within the map's own rows.
 */
export function struckFootprints(
  footprints: RegionMapFootprint[],
  eventAreaIds: number[]
): Set<number> {
  const out = new Set<number>();
  if (eventAreaIds.length === 0) return out;
  const roots = new Set(eventAreaIds);
  const parentOf = new Map(footprints.map((f) => [f.area_id, f.parent_id] as const));
  for (const footprint of footprints) {
    let node: number | null = footprint.area_id;
    const seen = new Set<number>();
    while (node != null && !seen.has(node)) {
      if (roots.has(node)) {
        out.add(footprint.area_id);
        break;
      }
      seen.add(node);
      node = parentOf.get(node) ?? null;
    }
  }
  return out;
}
