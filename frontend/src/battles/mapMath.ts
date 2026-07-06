/**
 * Pure map math for the battle map canvas (#2009).
 *
 * BattlePlace.x/y are the backend's plane coordinates (world/battles/models.py)
 * — arbitrary floats on a strategic plane, not grid-cell integers like the
 * building builder's grid_x/grid_y (buildings/gridMath.ts). planeToCanvas maps
 * a place's plane point into React Flow canvas space: the plane grows "up"
 * (north = +y) but the canvas grows down, so y is negated relative to the
 * bounds — mirrors gridMath.ts's cellToPosition comment.
 */

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

/** Plane-unit padding added around the tightest bounding box of the places. */
export const PADDING = 2;

/** Canvas pixels spanned by the wider of the bounds' two axes. */
export const CANVAS_SIZE = 800;

/**
 * Tight bounding box (+ padding) over a battle's places. A single place (or
 * several coincident places) has zero extent on its own — padding always
 * applies, so the result never degenerates to a zero-width/height box that
 * planeToCanvas/radiusToPixels would have nothing to scale against.
 */
export function computeBounds(places: PlanePoint[]): PlaneBounds {
  if (places.length === 0) {
    return { minX: -PADDING, maxX: PADDING, minY: -PADDING, maxY: PADDING };
  }
  const xs = places.map((p) => p.x);
  const ys = places.map((p) => p.y);
  return {
    minX: Math.min(...xs) - PADDING,
    maxX: Math.max(...xs) + PADDING,
    minY: Math.min(...ys) - PADDING,
    maxY: Math.max(...ys) + PADDING,
  };
}

/** Pixels-per-plane-unit, uniform across both axes so radii stay circular. */
function scaleFor(bounds: PlaneBounds): number {
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
 * sizes vary (PlaceNode clamps its rendered diameter at a minimum), so
 * without this offset larger/smaller nodes visually drift off their place's
 * true plane coordinate.
 */
export function centeredNodePosition(
  point: { x: number; y: number },
  sizePx: number
): { x: number; y: number } {
  return { x: point.x - sizePx / 2, y: point.y - sizePx / 2 };
}
