/**
 * Pure grid math for the building builder canvas (#670 PR2).
 *
 * The backend stores building-local cells (grid_x, grid_y, floor) where
 * north is +grid_y. Screens draw y downward, so rendering negates grid_y.
 * One cell per room regardless of size — size renders as a label, never
 * as footprint.
 */

export const CELL = 120;

/** Planar dig directions, mirroring world/buildings/room_constants.py. */
export const DIRECTIONS: Record<string, { dx: number; dy: number }> = {
  north: { dx: 0, dy: 1 },
  south: { dx: 0, dy: -1 },
  east: { dx: 1, dy: 0 },
  west: { dx: -1, dy: 0 },
  northeast: { dx: 1, dy: 1 },
  northwest: { dx: -1, dy: 1 },
  southeast: { dx: 1, dy: -1 },
  southwest: { dx: -1, dy: -1 },
};

export interface Cell {
  x: number;
  y: number;
}

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

export interface ExitRecord {
  id: number;
  name: string;
  from_room_id: number;
  to_room_id: number;
}

export interface ExitEdge {
  /** Stable per room pair: `exit-<lowRoomId>-<highRoomId>`. */
  id: string;
  source: number;
  target: number;
  /** Exit leaving `source` toward `target` (if any). */
  there: ExitRecord | null;
  /** Exit leaving `target` back toward `source` (if any). */
  back: ExitRecord | null;
}

/** Grid cell -> React Flow canvas position (top-left of the node). */
export function cellToPosition(cell: Cell): { x: number; y: number } {
  return { x: cell.x * CELL, y: -cell.y * CELL };
}

/** Canvas position -> nearest grid cell (inverse of cellToPosition). */
export function positionToCell(position: { x: number; y: number }): Cell {
  return { x: Math.round(position.x / CELL), y: Math.round(-position.y / CELL) };
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

/**
 * Pair directed exits into one edge per room pair. A one-way exit still
 * yields an edge (its `back` stays null).
 */
export function exitEdges(exits: ExitRecord[]): ExitEdge[] {
  const edges = new Map<string, ExitEdge>();
  for (const exit of exits) {
    const [low, high] = [
      Math.min(exit.from_room_id, exit.to_room_id),
      Math.max(exit.from_room_id, exit.to_room_id),
    ];
    const id = `exit-${low}-${high}`;
    let edge = edges.get(id);
    if (!edge) {
      edge = { id, source: exit.from_room_id, target: exit.to_room_id, there: null, back: null };
      edges.set(id, edge);
    }
    if (exit.from_room_id === edge.source) {
      edge.there = edge.there ?? exit;
    } else {
      edge.back = edge.back ?? exit;
    }
  }
  return [...edges.values()];
}
