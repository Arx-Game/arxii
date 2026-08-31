/**
 * latticeState (#3477 Task 5) — the Lattice's client-local sketch: planned
 * squares, carved voids, the grid's grown bounds, and (rooms mode) which
 * floors a viewer has grown beyond what's actually been dug. None of this
 * ever reaches the server (see the task brief's "plot-then-realize" ruling —
 * only Add/realize dispatches); it is pure per-account, per-node scratch
 * paper, so every read/write is try/catch wrapped the same way
 * `useAtlasState` treats its own localStorage.
 *
 * Split into pure state-transition functions (trivially unit-testable, no
 * DOM/storage involved) plus thin `read*`/`write*` persistence wrappers, so
 * `Lattice.tsx` can unit-test "empty -> plan -> void -> restore" without
 * mocking `localStorage` at all.
 */

export type CellKey = `${number},${number}`;

export function cellKey(x: number, y: number): CellKey {
  return `${x},${y}`;
}

export function parseCellKey(key: CellKey): [number, number] {
  const [x, y] = key.split(',').map(Number);
  return [x, y];
}

export interface Cardinal {
  name: string;
  opposite: string;
  dx: number;
  dy: number;
}

/**
 * North renders as +y, matching `world.areas.constants.DIRECTIONS` exactly.
 * Shared by `Lattice.tsx` and `document/Compass.tsx` (#3477 Task 6) — the
 * manuscript's 3×3 "where you stand" neighborhood needs the exact same
 * cardinal-naming/fallback math for its own ⊕-a-neighbor dig, so it lives
 * here rather than in either component (both are `react-refresh`-only-
 * exports-components files).
 */
export const CARDINALS: Cardinal[] = [
  { name: 'north', opposite: 'south', dx: 0, dy: 1 },
  { name: 'south', opposite: 'north', dx: 0, dy: -1 },
  { name: 'east', opposite: 'west', dx: 1, dy: 0 },
  { name: 'west', opposite: 'east', dx: -1, dy: 0 },
];

/** A non-cardinal (diagonal) neighbor still gets a real exit — just an unnamed one. */
export const FANCIFUL_EXIT_NAME = 'a fated passage';

/** The cardinal direction from `a` to `b`, or `null` when they aren't cardinally adjacent. */
export function directionBetween(
  a: { gridX: number | null; gridY: number | null },
  b: { gridX: number | null; gridY: number | null }
): Cardinal | null {
  const dx = (b.gridX ?? 0) - (a.gridX ?? 0);
  const dy = (b.gridY ?? 0) - (a.gridY ?? 0);
  return CARDINALS.find((dir) => dir.dx === dx && dir.dy === dy) ?? null;
}

export interface LatticeBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/** A grid with nothing on it yet still needs *some* ground to plot on. */
export const DEFAULT_BOUNDS: LatticeBounds = { minX: 0, maxX: 3, minY: 0, maxY: 2 };

export interface LatticeSketch {
  planned: CellKey[];
  voids: CellKey[];
  bounds: LatticeBounds;
}

export function emptySketch(bounds: LatticeBounds = DEFAULT_BOUNDS): LatticeSketch {
  return { planned: [], voids: [], bounds };
}

/**
 * The bounds must always contain every realized tile, even ones planted
 * before the viewer ever grew the grid (e.g. imported content, or another
 * GM's edit) — this widens `stored` to cover `tiles` without ever shrinking
 * ground the viewer already grew.
 */
export function boundsContaining(
  stored: LatticeBounds,
  tiles: { gridX: number; gridY: number }[]
): LatticeBounds {
  return tiles.reduce(
    (acc, tile) => ({
      minX: Math.min(acc.minX, tile.gridX),
      maxX: Math.max(acc.maxX, tile.gridX),
      minY: Math.min(acc.minY, tile.gridY),
      maxY: Math.max(acc.maxY, tile.gridY),
    }),
    stored
  );
}

/**
 * North renders as +y, east as +x (mirrors `world.areas.constants.DIRECTIONS`
 * — "north" is a real dispatched direction word, not just a screen label).
 * Growing an edge never shifts existing coordinates (unlike the prototype's
 * demo, which re-bases a 0-indexed JS array); real tiles carry absolute,
 * arbitrary-signed server coordinates, so growing "west" or "south" simply
 * lowers the bound — nothing already placed needs to move.
 */
export function growBounds(
  bounds: LatticeBounds,
  edge: 'north' | 'south' | 'east' | 'west'
): LatticeBounds {
  switch (edge) {
    case 'north':
      return { ...bounds, maxY: bounds.maxY + 1 };
    case 'south':
      return { ...bounds, minY: bounds.minY - 1 };
    case 'east':
      return { ...bounds, maxX: bounds.maxX + 1 };
    case 'west':
      return { ...bounds, minX: bounds.minX - 1 };
    default:
      return bounds;
  }
}

/** Plot a square — the empty-cell-always-digs ruling: one click plans it. */
export function planCell(sketch: LatticeSketch, key: CellKey): LatticeSketch {
  if (sketch.planned.includes(key)) return sketch;
  return { ...sketch, planned: [...sketch.planned, key] };
}

/** The plan's own "x" — remove a square from the plan without carving it. */
export function unplanCell(sketch: LatticeSketch, key: CellKey): LatticeSketch {
  return { ...sketch, planned: sketch.planned.filter((k) => k !== key) };
}

/**
 * The carve cycle (right-click, or the ✂ prune tool's click): a planned
 * square clears back to empty ground; empty ground is carved to a void;
 * a void restores back to empty ground. Realized tiles are never touched —
 * callers must not invoke this for an occupied cell.
 */
export function carveCell(sketch: LatticeSketch, key: CellKey): LatticeSketch {
  if (sketch.planned.includes(key)) return unplanCell(sketch, key);
  if (sketch.voids.includes(key)) {
    return { ...sketch, voids: sketch.voids.filter((k) => k !== key) };
  }
  return { ...sketch, voids: [...sketch.voids, key] };
}

function sketchStorageKey(
  accountId: number | string,
  mode: 'areas' | 'rooms',
  nodeId: number,
  floor: number | null
): string {
  const floorPart = floor == null ? '' : `:floor:${floor}`;
  return `world-builder-lattice:${accountId}:${mode}:${nodeId}${floorPart}`;
}

export function readLatticeSketch(
  accountId: number | string,
  mode: 'areas' | 'rooms',
  nodeId: number,
  floor: number | null,
  fallbackBounds: LatticeBounds = DEFAULT_BOUNDS
): LatticeSketch {
  try {
    const raw = window.localStorage.getItem(sketchStorageKey(accountId, mode, nodeId, floor));
    if (!raw) return emptySketch(fallbackBounds);
    const parsed = JSON.parse(raw) as Partial<LatticeSketch> | null;
    if (!parsed) return emptySketch(fallbackBounds);
    return {
      planned: Array.isArray(parsed.planned) ? (parsed.planned as CellKey[]) : [],
      voids: Array.isArray(parsed.voids) ? (parsed.voids as CellKey[]) : [],
      bounds: parsed.bounds ?? fallbackBounds,
    };
  } catch {
    return emptySketch(fallbackBounds);
  }
}

export function writeLatticeSketch(
  accountId: number | string,
  mode: 'areas' | 'rooms',
  nodeId: number,
  floor: number | null,
  sketch: LatticeSketch
): void {
  try {
    window.localStorage.setItem(
      sketchStorageKey(accountId, mode, nodeId, floor),
      JSON.stringify(sketch)
    );
  } catch {
    // Storage unavailable — the sketch is scratch paper, never a requirement.
  }
}

function floorsStorageKey(accountId: number | string, nodeId: number): string {
  return `world-builder-lattice:${accountId}:rooms:${nodeId}:grown-floors`;
}

export function readGrownFloors(accountId: number | string, nodeId: number): number[] {
  try {
    const raw = window.localStorage.getItem(floorsStorageKey(accountId, nodeId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((n) => typeof n === 'number') : [];
  } catch {
    return [];
  }
}

export function writeGrownFloors(
  accountId: number | string,
  nodeId: number,
  floors: number[]
): void {
  try {
    window.localStorage.setItem(floorsStorageKey(accountId, nodeId), JSON.stringify(floors));
  } catch {
    // Storage unavailable — floor growth is a convenience, not a requirement.
  }
}

/**
 * The floor rail is "data on the build, not chrome" (brief ruling): it always
 * shows every floor a real room already occupies, plus ground (0) as the
 * baseline for a building with nothing dug yet, plus whatever the viewer has
 * grown beyond that — highest floor first, matching a building's own top-down
 * reading order.
 */
export function computeFloorRail(dataFloors: number[], grownFloors: number[]): number[] {
  const all = new Set<number>([0, ...dataFloors, ...grownFloors]);
  return Array.from(all).sort((a, b) => b - a);
}

/** `edge` "up" adds one floor above the highest; "down" one below the lowest. */
export function growFloor(floors: number[], edge: 'up' | 'down'): number {
  if (floors.length === 0) return edge === 'up' ? 1 : -1;
  return edge === 'up' ? Math.max(...floors) + 1 : Math.min(...floors) - 1;
}
