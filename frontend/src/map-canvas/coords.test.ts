import { describe, expect, it } from 'vitest';

import {
  CANVAS_SIZE,
  CELL,
  cellToPosition,
  centeredNodePosition,
  computeBounds,
  PADDING,
  planeToCanvas,
  positionToCell,
  radiusToPixels,
  type PlaneBounds,
} from './coords';

describe('cellToPosition / positionToCell', () => {
  it('renders north (+grid_y) upward (negative screen y)', () => {
    expect(cellToPosition({ x: 0, y: 1 })).toEqual({ x: 0, y: -CELL });
    expect(cellToPosition({ x: 2, y: -1 })).toEqual({ x: 2 * CELL, y: CELL });
  });

  it('round-trips through a drag position with snapping', () => {
    const position = cellToPosition({ x: 3, y: 2 });
    expect(positionToCell({ x: position.x + CELL * 0.3, y: position.y - CELL * 0.2 })).toEqual({
      x: 3,
      y: 2,
    });
  });
});

describe('computeBounds', () => {
  it('spans the tightest box over known places plus padding', () => {
    const bounds = computeBounds([
      { x: 0, y: 0 },
      { x: 10, y: 4 },
    ]);
    expect(bounds).toEqual({
      minX: 0 - PADDING,
      maxX: 10 + PADDING,
      minY: 0 - PADDING,
      maxY: 4 + PADDING,
    });
  });

  it('pads a single place into a non-degenerate unit square', () => {
    const bounds = computeBounds([{ x: 5, y: 5 }]);
    expect(bounds).toEqual({
      minX: 5 - PADDING,
      maxX: 5 + PADDING,
      minY: 5 - PADDING,
      maxY: 5 + PADDING,
    });
    expect(bounds.maxX - bounds.minX).toBeGreaterThan(0);
    expect(bounds.maxY - bounds.minY).toBeGreaterThan(0);
  });

  it('falls back to origin-centered bounds with no places', () => {
    expect(computeBounds([])).toEqual({
      minX: -PADDING,
      maxX: PADDING,
      minY: -PADDING,
      maxY: PADDING,
    });
  });
});

describe('planeToCanvas', () => {
  const bounds: PlaneBounds = { minX: 0, maxX: 10, minY: 0, maxY: 10 };

  it('maps the bottom-left plane corner to the canvas origin', () => {
    expect(planeToCanvas({ x: 0, y: 0 }, bounds)).toEqual({ x: 0, y: CANVAS_SIZE });
  });

  it('negates y — higher plane y (north) renders nearer the canvas top', () => {
    const top = planeToCanvas({ x: 0, y: 10 }, bounds);
    const bottom = planeToCanvas({ x: 0, y: 0 }, bounds);
    expect(top.y).toBe(0);
    expect(top.y).toBeLessThan(bottom.y);
  });

  it('scales x proportionally to the bounds span', () => {
    expect(planeToCanvas({ x: 5, y: 0 }, bounds)).toEqual({ x: CANVAS_SIZE / 2, y: CANVAS_SIZE });
  });
});

describe('radiusToPixels', () => {
  it('scales a plane radius by the same factor as planeToCanvas', () => {
    const bounds: PlaneBounds = { minX: 0, maxX: 10, minY: 0, maxY: 10 };
    expect(radiusToPixels(2, bounds)).toBe(2 * (CANVAS_SIZE / 10));
  });

  it('falls back to a 1:1 scale for a zero-span bounds', () => {
    const bounds: PlaneBounds = { minX: 5, maxX: 5, minY: 5, maxY: 5 };
    expect(radiusToPixels(3, bounds)).toBe(3);
  });
});

describe('centeredNodePosition', () => {
  it('offsets a canvas point by half the node size on both axes', () => {
    expect(centeredNodePosition({ x: 100, y: 200 }, 40)).toEqual({ x: 80, y: 180 });
  });

  it('is a no-op offset for a zero-size node', () => {
    expect(centeredNodePosition({ x: 100, y: 200 }, 0)).toEqual({ x: 100, y: 200 });
  });
});
