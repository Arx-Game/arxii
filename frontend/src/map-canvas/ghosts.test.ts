import { describe, expect, it } from 'vitest';

import { ghostCells, type PlacedRoom } from './ghosts';

const room = (id: number, x: number | null, y: number | null, floor = 0): PlacedRoom => ({
  id,
  grid_x: x,
  grid_y: y,
  floor,
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
