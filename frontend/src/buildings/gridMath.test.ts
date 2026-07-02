import { describe, expect, it } from 'vitest';

import {
  CELL,
  cellToPosition,
  exitEdges,
  ghostCells,
  positionToCell,
  type ExitRecord,
  type PlacedRoom,
} from './gridMath';

const room = (id: number, x: number | null, y: number | null, floor = 0): PlacedRoom => ({
  id,
  grid_x: x,
  grid_y: y,
  floor,
});

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

describe('ghostCells', () => {
  it('surrounds a lone room with eight ghosts', () => {
    const ghosts = ghostCells([room(1, 0, 0)], 0);
    expect(ghosts).toHaveLength(8);
    expect(ghosts.every((g) => g.fromRoomId === 1)).toBe(true);
  });

  it('never proposes an occupied cell', () => {
    const ghosts = ghostCells([room(1, 0, 0), room(2, 1, 0)], 0);
    expect(ghosts.some((g) => g.x === 1 && g.y === 0)).toBe(false);
    expect(ghosts.some((g) => g.x === 0 && g.y === 0)).toBe(false);
  });

  it('dedupes shared neighbours to one ghost', () => {
    const ghosts = ghostCells([room(1, 0, 0), room(2, 2, 0)], 0);
    const at = ghosts.filter((g) => g.x === 1 && g.y === 0);
    expect(at).toHaveLength(1);
  });

  it('ignores unplaced rooms and other floors', () => {
    expect(ghostCells([room(1, null, null)], 0)).toHaveLength(0);
    expect(ghostCells([room(1, 0, 0, 1)], 0)).toHaveLength(0);
  });

  it('labels the ghost with the dig direction from its source room', () => {
    const ghosts = ghostCells([room(1, 0, 0)], 0);
    const north = ghosts.find((g) => g.x === 0 && g.y === 1);
    expect(north?.direction).toBe('north');
  });
});

describe('exitEdges', () => {
  const exit = (id: number, name: string, from: number, to: number): ExitRecord => ({
    id,
    name,
    from_room_id: from,
    to_room_id: to,
  });

  it('pairs a two-way link into one edge', () => {
    const edges = exitEdges([exit(10, 'east', 1, 2), exit(11, 'west', 2, 1)]);
    expect(edges).toHaveLength(1);
    expect(edges[0].there?.name).toBe('east');
    expect(edges[0].back?.name).toBe('west');
  });

  it('keeps a one-way exit as an edge with a null back', () => {
    const edges = exitEdges([exit(10, 'chute', 3, 4)]);
    expect(edges).toHaveLength(1);
    expect(edges[0].there?.name).toBe('chute');
    expect(edges[0].back).toBeNull();
  });

  it('gives parallel pairs a stable id per room pair', () => {
    const edges = exitEdges([exit(10, 'east', 1, 2), exit(11, 'west', 2, 1)]);
    expect(edges[0].id).toBe('exit-1-2');
  });
});
