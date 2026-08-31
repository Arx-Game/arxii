/**
 * Shared Atlas constants (#3477 fix round 1) — hoisted out of `AtlasPage`,
 * `AreaPage`, and `IndexRail`, which each independently declared the same
 * `BUILDING_LEVEL` constant and the same "does this area hold child areas or
 * rooms directly" kind ternary.
 */
import type { AtlasViewKind } from './useAtlasState';

/** Mirrors `world.areas.constants.AreaLevel.BUILDING` (see `../types.ts`'s `AREA_LEVELS`). */
export const BUILDING_LEVEL = 10;

/**
 * A BUILDING-level area holds rooms directly — its Atlas view is the room
 * grid (`'roomgrid'`, Task 5's `<Lattice mode="rooms"/>`). Anything above
 * BUILDING can hold child areas of its own (`'area'`, `<Lattice
 * mode="areas"/>`) — see `AreaPage`'s ledger-vs-lattice-only split.
 */
export function areaViewKind(level: number): AtlasViewKind {
  return level === BUILDING_LEVEL ? 'roomgrid' : 'area';
}
