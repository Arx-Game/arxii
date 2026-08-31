/**
 * Shared Atlas constants (#3477 fix round 1) — hoisted out of `AtlasPage`,
 * `AreaPage`, and `IndexRail`, which each independently declared the same
 * `BUILDING_LEVEL` constant and the same "does this area hold child areas or
 * rooms directly" kind ternary.
 */
import { AREA_LEVELS } from '../types';
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

const ORDERED_LEVELS = AREA_LEVELS.map((choice) => choice.value).sort((a, b) => a - b);

/**
 * The level a plotted square realizes into on an `'areas'`-mode `<Lattice/>`
 * (Task 5) — one step down the `AreaLevel` ladder from `level`, e.g. a Ward
 * (30) plots Neighborhoods/Buildings (whichever sits directly below it,
 * currently Neighborhood at 20). Never called for a BUILDING area itself
 * (its Lattice is `'rooms'` mode, which realizes rooms, not child areas).
 */
export function childLevelOf(level: number): number {
  const index = ORDERED_LEVELS.indexOf(level);
  if (index <= 0) return BUILDING_LEVEL;
  return ORDERED_LEVELS[index - 1];
}
