/**
 * Pure grid math specific to the building builder canvas (#670 PR2) — dig
 * directions. The shared grid coordinate conversions (`CELL`,
 * `cellToPosition`/`positionToCell`), exit-edge pairing (`exitEdges`), and
 * ghost-cell (empty adjacent cell) computation (`ghostCells`) moved to
 * `@/map-canvas` (#2449) so the world-builder canvas can reuse them too —
 * see `@/map-canvas/ghosts`.
 *
 * The backend stores building-local cells (grid_x, grid_y, floor) where
 * north is +grid_y — see `@/map-canvas/coords` for the y-negation
 * convention.
 */

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
