/**
 * Pure layout math for the drawn battle map (#4670, slice 1 of #4651).
 *
 * A place is drawn as an area of squares. A staff-authored area (area_x/y/w/h on the
 * place) is used verbatim; a place built before areas existed gets a 3x2 area at its
 * tactical-layout point, so every older room still draws. An aerial place (kind
 * `aerial` over an anchor) has no area of its own: the map draws it over its anchor.
 *
 * Squares are drawing only. Nothing here feeds a rule; the server owns where a
 * character may stand.
 */

import type { LayoutPoint, TacticalNode } from '@/areas/tacticalLayout';

/** One square's side, in viewBox units. */
export const CELL = 40;

const DERIVED_W = 3;
const DERIVED_H = 2;

export interface AreaNode extends TacticalNode {
  area_x: number | null;
  area_y: number | null;
  area_w: number | null;
  area_h: number | null;
}

export interface MapArea {
  x: number;
  y: number;
  w: number;
  h: number;
  /** True when the place has no authored area and this one came from its layout point. */
  derived: boolean;
}

export interface Square {
  x: number;
  y: number;
}

export interface SquaredOccupant {
  square: Square | null;
}

export interface PlacedToken<T> {
  occupant: T;
  x: number;
  y: number;
}

/** An aerial place drawn over its anchor rather than as an area of its own. */
export function isAerialOverlay(node: TacticalNode): boolean {
  return node.kind === 'aerial' && node.elevation_anchor_id !== null;
}

export function placeAreas(
  nodes: AreaNode[],
  layoutPoints: Map<number, LayoutPoint>
): Map<number, MapArea> {
  const areas = new Map<number, MapArea>();
  const ids = new Set(nodes.map((n) => n.id));
  for (const node of nodes) {
    // Drawn over its anchor; an aerial place whose anchor is missing gets an area.
    if (isAerialOverlay(node) && ids.has(node.elevation_anchor_id!)) continue;
    if (
      node.area_x !== null &&
      node.area_y !== null &&
      node.area_w !== null &&
      node.area_h !== null
    ) {
      areas.set(node.id, {
        x: node.area_x,
        y: node.area_y,
        w: node.area_w,
        h: node.area_h,
        derived: false,
      });
      continue;
    }
    const point = layoutPoints.get(node.id) ?? { x: 0, y: 0 };
    areas.set(node.id, {
      x: Math.round(point.x / CELL),
      y: Math.round(point.y / CELL),
      w: DERIVED_W,
      h: DERIVED_H,
      derived: true,
    });
  }
  return areas;
}

function insideArea(area: MapArea, square: Square): boolean {
  return (
    square.x >= area.x &&
    square.x < area.x + area.w &&
    square.y >= area.y &&
    square.y < area.y + area.h
  );
}

const keyOf = (x: number, y: number) => `${x},${y}`;

export interface TokenSquareOptions {
  /** Squares already drawn on (another place's tokens over the same ground). */
  blocked?: ReadonlySet<string>;
  /** Fill free squares from the bottom-right instead of the top-left. */
  fromEnd?: boolean;
}

/**
 * Where each occupant's token sits: an occupant whose square lies inside the area keeps
 * it; the rest fill free squares row-major; when the area is full they stack on the
 * last square.
 */
export function tokenSquares<T extends SquaredOccupant>(
  area: MapArea,
  occupants: T[],
  options: TokenSquareOptions = {}
): PlacedToken<T>[] {
  const taken = new Set<string>(options.blocked ?? []);
  const placed: (PlacedToken<T> | null)[] = occupants.map(() => null);

  occupants.forEach((occupant, index) => {
    const square = occupant.square;
    if (square && insideArea(area, square) && !taken.has(keyOf(square.x, square.y))) {
      taken.add(keyOf(square.x, square.y));
      placed[index] = { occupant, x: square.x, y: square.y };
    }
  });

  // The top row carries the place's name label: an area two or more rows tall fills
  // from its second row and reaches the top row only when the rest is full.
  const rowSquares = (row: number): Square[] => {
    const squares: Square[] = [];
    for (let col = 0; col < area.w; col++) {
      const x = area.x + col;
      const y = area.y + row;
      if (!taken.has(keyOf(x, y))) squares.push({ x, y });
    }
    return squares;
  };
  const lower: Square[] = [];
  for (let row = area.h >= 2 ? 1 : 0; row < area.h; row++) lower.push(...rowSquares(row));
  if (options.fromEnd) lower.reverse();
  const top = area.h >= 2 ? rowSquares(0) : [];
  if (options.fromEnd) top.reverse();
  const free = [...lower, ...top];
  const last = options.fromEnd
    ? { x: area.x, y: area.y }
    : { x: area.x + area.w - 1, y: area.y + area.h - 1 };

  let next = 0;
  return occupants.map((occupant, index) => {
    const kept = placed[index];
    if (kept) return kept;
    const square = free[next] ?? free[free.length - 1] ?? last;
    if (next < free.length) next += 1;
    return { occupant, x: square.x, y: square.y };
  });
}

/** The viewBox (in px) around every area, with one square of margin. */
export function mapBounds(areas: Iterable<MapArea>): {
  x: number;
  y: number;
  w: number;
  h: number;
} {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const a of areas) {
    minX = Math.min(minX, a.x);
    minY = Math.min(minY, a.y);
    maxX = Math.max(maxX, a.x + a.w);
    maxY = Math.max(maxY, a.y + a.h);
  }
  if (minX === Infinity) return { x: 0, y: 0, w: 4 * CELL, h: 3 * CELL };
  return {
    x: (minX - 1) * CELL,
    y: (minY - 1) * CELL,
    w: (maxX - minX + 2) * CELL,
    h: (maxY - minY + 2) * CELL,
  };
}
