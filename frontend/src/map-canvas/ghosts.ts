/**
 * Ghost-cell (empty adjacent cell) computation, shared by the building
 * builder canvas (#670 PR2) and the staff world-builder canvas (#2449) —
 * moved here from `@/buildings/gridMath` so both canvases depend on the
 * shared primitive rather than one app importing the other's internals
 * (fix pass, task-6 report).
 *
 * `DIRECTIONS` stays in `@/buildings/gridMath` (it's a building-dig-specific
 * concept — mirrors `world/buildings/room_constants.py` and feeds
 * `DigDialog`'s direction picker) but is re-used here purely as the offset
 * table for computing which empty cells are adjacent to a placed room.
 *
 * One cell per room regardless of size — size renders as a label, never as
 * footprint. The backend stores building/area-local cells (grid_x, grid_y,
 * floor) where north is +grid_y — see `./coords.ts` for the y-negation
 * convention.
 */

import type { Cell } from './coords';

/** Planar dig directions, mirroring world/buildings/room_constants.py. */
const DIRECTIONS: Record<string, { dx: number; dy: number }> = {
  north: { dx: 0, dy: 1 },
  south: { dx: 0, dy: -1 },
  east: { dx: 1, dy: 0 },
  west: { dx: -1, dy: 0 },
  northeast: { dx: 1, dy: 1 },
  northwest: { dx: -1, dy: 1 },
  southeast: { dx: 1, dy: -1 },
  southwest: { dx: -1, dy: -1 },
};

export interface PlacedRoom {
  id: number;
  grid_x: number | null;
  grid_y: number | null;
  floor: number;
}

export interface GhostCell extends Cell {
  fromRoomId: number;
  direction: string;
}

const cellKey = (x: number, y: number) => `${x},${y}`;

/**
 * Empty cells adjacent to placed rooms on this floor — the click-to-dig
 * targets. Occupied cells are skipped; when two rooms share an empty
 * neighbour the first room (payload order) claims the ghost.
 */
export function ghostCells(rooms: PlacedRoom[], floor: number): GhostCell[] {
  const onFloor = rooms.filter(
    (room) => room.floor === floor && room.grid_x !== null && room.grid_y !== null
  );
  const occupied = new Set(onFloor.map((room) => cellKey(room.grid_x!, room.grid_y!)));
  const ghosts = new Map<string, GhostCell>();
  for (const room of onFloor) {
    for (const [direction, { dx, dy }] of Object.entries(DIRECTIONS)) {
      const x = room.grid_x! + dx;
      const y = room.grid_y! + dy;
      const key = cellKey(x, y);
      if (occupied.has(key) || ghosts.has(key)) continue;
      ghosts.set(key, { x, y, fromRoomId: room.id, direction });
    }
  }
  return [...ghosts.values()];
}
