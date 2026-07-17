/**
 * Shared coordinate math for map canvases built on React Flow — the building
 * builder canvas (#670) and the battle map canvas (#2009), and (#2449) the
 * staff world-builder canvas that reuses both.
 *
 * Two independent coordinate systems live here, both following **one
 * y-negation convention**: the domain grows "up" (north = +y), but React
 * Flow's canvas grows downward, so y is always negated (or mirrored against
 * a bounding box) when converting a domain point into canvas space.
 *
 * - **Grid** (buildings): integer cells (`grid_x`, `grid_y`) straight from
 *   the backend, one cell per room, `CELL` px per cell, no origin offset —
 *   `cellToPosition` negates y directly.
 * - **Plane** (battles): arbitrary float coordinates (`x`, `y`) on a
 *   strategic plane, not anchored at a fixed origin — `planeToCanvas`
 *   negates y relative to a bounding box (`computeBounds`) instead.
 */

export const CELL = 120;

export interface Cell {
  x: number;
  y: number;
}

/** Grid cell -> React Flow canvas position (top-left of the node). */
export function cellToPosition(cell: Cell): { x: number; y: number } {
  return { x: cell.x * CELL, y: -cell.y * CELL };
}

/** Canvas position -> nearest grid cell (inverse of cellToPosition). */
export function positionToCell(position: { x: number; y: number }): Cell {
  return { x: Math.round(position.x / CELL), y: Math.round(-position.y / CELL) };
}

export interface PlanePoint {
  x: number;
  y: number;
}

export interface PlaneBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/** Plane-unit padding added around the tightest bounding box of a set of points. */
export const PADDING = 2;

/** Canvas pixels spanned by the wider of the bounds' two axes. */
export const CANVAS_SIZE = 800;

/**
 * Tight bounding box (+ padding) over a set of plane points. A single point
 * (or several coincident points) has zero extent on its own — padding always
 * applies, so the result never degenerates to a zero-width/height box that
 * planeToCanvas/radiusToPixels would have nothing to scale against.
 */
export function computeBounds(points: PlanePoint[]): PlaneBounds {
  if (points.length === 0) {
    return { minX: -PADDING, maxX: PADDING, minY: -PADDING, maxY: PADDING };
  }
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return {
    minX: Math.min(...xs) - PADDING,
    maxX: Math.max(...xs) + PADDING,
    minY: Math.min(...ys) - PADDING,
    maxY: Math.max(...ys) + PADDING,
  };
}

/** Pixels-per-plane-unit, uniform across both axes so radii stay circular. */
export function scaleFor(bounds: PlaneBounds): number {
  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;
  const span = Math.max(width, height);
  return span > 0 ? CANVAS_SIZE / span : 1;
}

/** Plane point -> React Flow canvas position. y is negated (see module doc). */
export function planeToCanvas(p: PlanePoint, bounds: PlaneBounds): { x: number; y: number } {
  const scale = scaleFor(bounds);
  return {
    x: (p.x - bounds.minX) * scale,
    y: (bounds.maxY - p.y) * scale,
  };
}

/** Plane-unit radius (e.g. footprint_radius) -> canvas pixels, same scale as planeToCanvas. */
export function radiusToPixels(r: number, bounds: PlaneBounds): number {
  return r * scaleFor(bounds);
}

/**
 * Offset a canvas point (e.g. planeToCanvas's output) into a node's top-left
 * position so the node is centered on that point rather than anchored there
 * by its corner. React Flow positions nodes by top-left corner, but node
 * sizes vary (e.g. PlaceNode clamps its rendered diameter at a minimum), so
 * without this offset larger/smaller nodes visually drift off their true
 * domain coordinate.
 */
export function centeredNodePosition(
  point: { x: number; y: number },
  sizePx: number
): { x: number; y: number } {
  return { x: point.x - sizePx / 2, y: point.y - sizePx / 2 };
}
