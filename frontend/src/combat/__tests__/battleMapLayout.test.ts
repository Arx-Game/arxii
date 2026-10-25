import { describe, expect, it } from 'vitest';
import { CELL, mapBounds, placeAreas, tokenSquares } from '../battleMapLayout';
import type { AreaNode, MapArea } from '../battleMapLayout';

function node(overrides: Partial<AreaNode> & { id: number }): AreaNode {
  return {
    kind: 'feature',
    elevation_anchor_id: null,
    layout_x: null,
    layout_y: null,
    area_x: null,
    area_y: null,
    area_w: null,
    area_h: null,
    ...overrides,
  };
}

describe('placeAreas', () => {
  it('uses an authored area verbatim', () => {
    const areas = placeAreas(
      [node({ id: 1, area_x: 2, area_y: 2, area_w: 8, area_h: 9 })],
      new Map([[1, { x: 400, y: 400 }]])
    );
    expect(areas.get(1)).toEqual({ x: 2, y: 2, w: 8, h: 9, derived: false });
  });

  it('derives a 3x2 area from the layout point when none is authored', () => {
    const areas = placeAreas([node({ id: 1 })], new Map([[1, { x: 161, y: -118 }]]));
    expect(areas.get(1)).toEqual({ x: 4, y: -3, w: 3, h: 2, derived: true });
  });

  it('gives an aerial place over an anchor no area of its own', () => {
    const areas = placeAreas(
      [
        node({ id: 1, area_x: 0, area_y: 0, area_w: 4, area_h: 4 }),
        node({ id: 2, kind: 'aerial', elevation_anchor_id: 1 }),
      ],
      new Map([
        [1, { x: 0, y: 0 }],
        [2, { x: 0, y: -120 }],
      ])
    );
    expect(areas.has(1)).toBe(true);
    expect(areas.has(2)).toBe(false);
  });
});

describe('tokenSquares', () => {
  const area: MapArea = { x: 2, y: 3, w: 2, h: 2, derived: false };

  it('keeps a square inside the area', () => {
    const placed = tokenSquares(area, [{ name: 'A', square: { x: 3, y: 4 } }]);
    expect(placed.map((p) => [p.x, p.y])).toEqual([[3, 4]]);
  });

  it('fills the rest row-major from the second row, leaving the label row for last', () => {
    const placed = tokenSquares(area, [
      { name: 'A', square: null },
      { name: 'B', square: { x: 2, y: 3 } },
      { name: 'C', square: { x: 9, y: 9 } },
      { name: 'D', square: null },
    ]);
    expect(placed.map((p) => [p.occupant.name, p.x, p.y])).toEqual([
      ['A', 2, 4],
      ['B', 2, 3],
      ['C', 3, 4],
      ['D', 3, 3],
    ]);
  });

  it('fills the top row of a one-row area', () => {
    const strip: MapArea = { x: 0, y: 0, w: 3, h: 1, derived: true };
    const placed = tokenSquares(strip, [
      { name: 'A', square: null },
      { name: 'B', square: null },
    ]);
    expect(placed.map((p) => [p.x, p.y])).toEqual([
      [0, 0],
      [1, 0],
    ]);
  });

  it('fills from the bottom-right, still leaving the label row for last', () => {
    const placed = tokenSquares(
      area,
      ['A', 'B', 'C'].map((name) => ({ name, square: null })),
      { fromEnd: true }
    );
    expect(placed.map((p) => [p.x, p.y])).toEqual([
      [3, 4],
      [2, 4],
      [3, 3],
    ]);
  });

  it('stacks overflow on the last free square', () => {
    const placed = tokenSquares(
      area,
      ['A', 'B', 'C', 'D', 'E', 'F'].map((name) => ({ name, square: null }))
    );
    expect(placed.map((p) => [p.x, p.y])).toEqual([
      [2, 4],
      [3, 4],
      [2, 3],
      [3, 3],
      [3, 3],
      [3, 3],
    ]);
  });

  it('never puts two kept occupants on one square', () => {
    const placed = tokenSquares(area, [
      { name: 'A', square: { x: 2, y: 3 } },
      { name: 'B', square: { x: 2, y: 3 } },
    ]);
    expect(placed.map((p) => [p.x, p.y])).toEqual([
      [2, 3],
      [2, 4],
    ]);
  });
});

describe('mapBounds', () => {
  it('wraps every area with one square of margin', () => {
    expect(
      mapBounds([
        { x: 0, y: 0, w: 2, h: 2, derived: false },
        { x: 4, y: -1, w: 3, h: 2, derived: true },
      ])
    ).toEqual({ x: -CELL, y: -2 * CELL, w: 9 * CELL, h: 5 * CELL });
  });
});
