/**
 * The carve tools' arithmetic (#4905), kept pure so it runs without a canvas: a brush
 * square, a flood over a landmass, a flood over the pips a domain holds, and the land
 * inside a drawn loop. Everything works on the region payload the page already holds;
 * the server stays the authority and skips any pip the client got wrong.
 */
import type { RegionMapFootprint, RegionMapPips } from '../types';
import { footprintAt, pipKey, regionBounds } from './regionMapCanvas';

export type Pip = [number, number];

/** A ladder row, as much of it as the fills read. */
export interface LadderLink {
  title_id: number;
  parent_title_id: number | null;
}

export const BRUSH_WIDTHS = [1, 3, 7] as const;
export type BrushWidth = (typeof BRUSH_WIDTHS)[number];

const WATER_TERRAINS = new Set(['water', 'lake']);

/** The width×width square of pips centred on the pointer's pip. */
export function brushPips(center: Pip, width: BrushWidth): Pip[] {
  const half = Math.floor(width / 2);
  const out: Pip[] = [];
  for (let dy = -half; dy <= half; dy += 1) {
    for (let dx = -half; dx <= half; dx += 1) {
      out.push([center[0] + dx, center[1] + dy]);
    }
  }
  return out;
}

/** Every title above `titleId` on the ladder, walked by `parent_title_id`. */
export function ancestorTitleIds(rows: readonly LadderLink[], titleId: number): Set<number> {
  const parents = new Map(rows.map((row) => [row.title_id, row.parent_title_id]));
  const out = new Set<number>();
  let next = parents.get(titleId) ?? null;
  while (next != null && !out.has(next)) {
    out.add(next);
    next = parents.get(next) ?? null;
  }
  return out;
}

/**
 * Whether a carve for `targetTitleId` may take a pip whose lowest holder is `holder`:
 * open ground, the target itself, an ancestor (the row moves down) or a descendant
 * (already inside). Anyone else's pip is a boundary.
 */
export function isTakeable(
  holder: RegionMapFootprint | null,
  targetTitleId: number,
  rows: readonly LadderLink[]
): boolean {
  if (holder == null || holder.title_id == null) return holder == null;
  if (holder.title_id === targetTitleId) return true;
  if (ancestorTitleIds(rows, targetTitleId).has(holder.title_id)) return true;
  return ancestorTitleIds(rows, holder.title_id).has(targetTitleId);
}

type Grid = {
  x0: number;
  y0: number;
  width: number;
  height: number;
  landAt: (x: number, y: number) => boolean;
  inside: (x: number, y: number) => boolean;
};

function gridOf(data: RegionMapPips): Grid {
  const b = regionBounds(data.region);
  const terrain = new Map<string, string>();
  for (const [x, y, kind] of data.pips) terrain.set(pipKey(x, y), kind);
  const inside = (x: number, y: number) =>
    x >= b.x0 && y >= b.y0 && x < b.x0 + b.width && y < b.y0 + b.height;
  const landAt = (x: number, y: number) => {
    const kind = terrain.get(pipKey(x, y));
    return kind != null && !WATER_TERRAINS.has(kind);
  };
  return { x0: b.x0, y0: b.y0, width: b.width, height: b.height, landAt, inside };
}

const NEIGHBOURS: Pip[] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];

/** A 4-connected flood from `start` over the pips `admits` accepts, inside the region. */
function flood(grid: Grid, start: Pip, admits: (x: number, y: number) => boolean): Pip[] {
  if (!grid.inside(start[0], start[1]) || !admits(start[0], start[1])) return [];
  const seen = new Set<string>([pipKey(start[0], start[1])]);
  const out: Pip[] = [];
  const stack: Pip[] = [start];
  while (stack.length > 0) {
    const [x, y] = stack.pop() as Pip;
    out.push([x, y]);
    for (const [dx, dy] of NEIGHBOURS) {
      const nx = x + dx;
      const ny = y + dy;
      const key = pipKey(nx, ny);
      if (seen.has(key) || !grid.inside(nx, ny) || !admits(nx, ny)) continue;
      seen.add(key);
      stack.push([nx, ny]);
    }
  }
  return out;
}

/** A pip's lowest holder, memoised per call: `footprintAt` scans every footprint. */
function holderIndex(footprints: RegionMapFootprint[]) {
  const cache = new Map<string, RegionMapFootprint | null>();
  return (x: number, y: number): RegionMapFootprint | null => {
    const key = pipKey(x, y);
    let hit = cache.get(key);
    if (hit === undefined) {
      hit = footprintAt(footprints, x, y);
      cache.set(key, hit);
    }
    return hit;
  };
}

/**
 * The landmass under `start`: connected land, stopping at water and at any pip held
 * by a domain that is neither the target nor on its ladder line.
 */
export function floodLand(
  data: RegionMapPips,
  start: Pip,
  targetTitleId: number,
  rows: readonly LadderLink[]
): Pip[] {
  const grid = gridOf(data);
  const holderOf = holderIndex(data.footprints);
  const takeable = new Map<number | null, boolean>();
  const admits = (x: number, y: number) => {
    if (!grid.landAt(x, y)) return false;
    const holder = holderOf(x, y);
    const id = holder?.area_id ?? null;
    let ok = takeable.get(id);
    if (ok === undefined) {
      ok = isTakeable(holder, targetTitleId, rows);
      takeable.set(id, ok);
    }
    return ok;
  };
  return flood(grid, start, admits);
}

/** The connected pips the target itself holds under `start`, for shift+Fill. */
export function floodHeld(data: RegionMapPips, start: Pip, targetTitleId: number): Pip[] {
  const grid = gridOf(data);
  const holderOf = holderIndex(data.footprints);
  return flood(grid, start, (x, y) => holderOf(x, y)?.title_id === targetTitleId);
}

/** Every pip on the straight line from `a` to `b`, both ends included (Bresenham). */
function line(a: Pip, b: Pip): Pip[] {
  const out: Pip[] = [];
  let [x, y] = a;
  const [x1, y1] = b;
  const dx = Math.abs(x1 - x);
  const dy = -Math.abs(y1 - y);
  const sx = x < x1 ? 1 : -1;
  const sy = y < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    out.push([x, y]);
    if (x === x1 && y === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y += sy;
    }
  }
  return out;
}

/**
 * The land inside a drawn loop, the path's own pips included. Consecutive samples are
 * joined with a line and the path closes back to its start, so a fast drag at low zoom
 * leaves no gap; the exterior is flooded from the region's border and everything else
 * is inside.
 */
export function loopInterior(data: RegionMapPips, path: Pip[]): Pip[] {
  if (path.length === 0) return [];
  const grid = gridOf(data);
  const onPath = new Set<string>();
  for (let i = 0; i < path.length; i += 1) {
    const next = path[(i + 1) % path.length];
    for (const [x, y] of line(path[i], next)) onPath.add(pipKey(x, y));
  }
  const exterior = new Set<string>();
  const offPath = (x: number, y: number) => !onPath.has(pipKey(x, y));
  const x1 = grid.x0 + grid.width - 1;
  const y1 = grid.y0 + grid.height - 1;
  const border: Pip[] = [];
  for (let x = grid.x0; x <= x1; x += 1) border.push([x, grid.y0], [x, y1]);
  for (let y = grid.y0; y <= y1; y += 1) border.push([grid.x0, y], [x1, y]);
  for (const start of border) {
    if (exterior.has(pipKey(start[0], start[1]))) continue;
    for (const [x, y] of flood(grid, start, offPath)) exterior.add(pipKey(x, y));
  }
  const out: Pip[] = [];
  for (let y = grid.y0; y <= y1; y += 1) {
    for (let x = grid.x0; x <= x1; x += 1) {
      if (!exterior.has(pipKey(x, y)) && grid.landAt(x, y)) out.push([x, y]);
    }
  }
  return out;
}
