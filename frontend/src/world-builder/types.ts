/**
 * Types for the staff world-builder canvas (#2449) — thin aliases over the
 * generated schema (Task 4) plus the Task 3 action-key union and the two
 * client-side choice lists the create/edit forms need (mirrors backend
 * TextChoices/IntegerChoices — the server remains the source of truth; these
 * are display options only).
 */
import type { components } from '@/generated/api';

export type WorldBuilderArea = components['schemas']['WorldBuilderArea'];
export type WorldBuilderAreaManager = components['schemas']['WorldBuilderAreaManager'];
export type WorldBuilderRoom = components['schemas']['WorldBuilderRoom'];
export type WorldBuilderPortalAnchor = components['schemas']['WorldBuilderPortalAnchor'];
export type WorldBuilderExit = components['schemas']['WorldBuilderExit'];
export type PaginatedWorldBuilderAreaList = components['schemas']['PaginatedWorldBuilderAreaList'];

/** Registry keys of the staff world-builder actions this surface dispatches (#2449 Task 3). */
export type WorldBuilderActionKey =
  | 'create_area'
  | 'edit_area'
  | 'staff_dig_room'
  | 'staff_edit_room'
  | 'staff_publish_room'
  | 'staff_set_room_desc_variant'
  | 'staff_remove_room_desc_variant'
  | 'staff_link_rooms'
  | 'staff_unlink_rooms'
  | 'staff_rename_exit'
  | 'staff_place_room'
  | 'staff_remove_room'
  | 'staff_remove_area'
  | 'staff_move_room'
  | 'staff_set_room_stat'
  | 'staff_add_place'
  | 'staff_edit_place'
  | 'staff_remove_place'
  | 'staff_add_ambient_line'
  | 'staff_remove_ambient_line'
  | 'staff_add_ambient_emit'
  | 'staff_remove_ambient_emit'
  | 'staff_install_room_feature'
  | 'staff_remove_room_feature'
  | 'staff_assign_functionary'
  | 'staff_remove_functionary'
  | 'staff_set_travel_hub'
  | 'staff_set_room_blueprint'
  | 'staff_set_starting_room'
  | 'staff_set_exit_detail'
  | 'staff_duplicate_room'
  | 'staff_batch_dig'
  | 'promote_room'
  | 'promote_area'
  | 'staff_place_clue'
  | 'staff_remove_clue'
  | 'staff_place_clue_trigger'
  | 'staff_remove_clue_trigger'
  | 'staff_place_portal_anchor'
  | 'staff_remove_portal_anchor';

/** Selection-time room detail (#3269) — mirrors WorldBuilderRoomDetailSerializer. */
export type WorldBuilderBreadcrumbEntry = components['schemas']['WorldBuilderBreadcrumb'];

/**
 * Thin alias over the generated schema (#3477 Task 6 — this used to be a
 * hand-rolled duplicate that had drifted: it was missing `conditions` on
 * ambient lines, entirely by hand where `WorldBuilderExitDetail`/
 * `WorldBuilderComfort`/`WorldBuilderAmbientLine`/`WorldBuilderAmbientEmit`
 * already exist generated. Aliasing keeps this one definition in sync with
 * the backend serializer by construction.
 */
export type WorldBuilderRoomDetail = components['schemas']['WorldBuilderRoomDetail'];
export type WorldBuilderExitDetail = components['schemas']['WorldBuilderExitDetail'];
export type WorldBuilderComfort = components['schemas']['WorldBuilderComfort'];
export type WorldBuilderAmbientLine = components['schemas']['WorldBuilderAmbientLine'];
export type WorldBuilderAmbientCondition = components['schemas']['WorldBuilderAmbientCondition'];
export type WorldBuilderRoomDescVariant = components['schemas']['WorldBuilderRoomDescVariant'];
export type WorldBuilderResonanceReading = components['schemas']['WorldBuilderResonanceReading'];
export type WorldBuilderGrant = components['schemas']['WorldBuilderGrant'];
export type WorldBuilderGrants = components['schemas']['WorldBuilderGrants'];

/** One cross-area room-search hit (#3269) — mirrors WorldBuilderRoomHitSerializer. */
export interface WorldBuilderRoomHit {
  id: number;
  name: string;
  area_id: number | null;
  area_name: string | null;
  floor: number;
  fixture_key: string | null;
}

/** Mirrors `world.areas.constants.AreaLevel` — select options for CreateAreaDialog. */
export const AREA_LEVELS: { value: number; label: string }[] = [
  { value: 10, label: 'Building' },
  { value: 20, label: 'Neighborhood' },
  { value: 30, label: 'Ward' },
  { value: 40, label: 'City' },
  { value: 50, label: 'Region' },
  { value: 60, label: 'Kingdom' },
  { value: 70, label: 'Continent' },
  { value: 80, label: 'World' },
  { value: 90, label: 'Plane' },
];

/** Mirrors `evennia_extensions.constants.RoomEnclosure` — select options for RoomDetailPanel. */
export const ROOM_ENCLOSURES: { value: string; label: string }[] = [
  { value: 'open_air', label: 'Open-air' },
  { value: 'roofed', label: 'Roofed' },
  { value: 'walled', label: 'Walled' },
  { value: 'sealed', label: 'Sealed' },
];

/** Mirrors `evennia_extensions.constants.ExitKind` — select options for ExitEditorDialog. */
export const EXIT_KINDS: { value: string; label: string }[] = [
  { value: 'door', label: 'Door' },
  { value: 'window', label: 'Window' },
];

/** Mirrors `world.game_clock.constants.Season` — select options for VariantsPanel. */
export const SEASONS: { value: string; label: string }[] = [
  { value: 'spring', label: 'Spring' },
  { value: 'summer', label: 'Summer' },
  { value: 'autumn', label: 'Autumn' },
  { value: 'winter', label: 'Winter' },
];

/** Mirrors `world.game_clock.constants.TimePhase` — select options for VariantsPanel. */
export const TIME_PHASES: { value: string; label: string }[] = [
  { value: 'dawn', label: 'Dawn' },
  { value: 'day', label: 'Day' },
  { value: 'dusk', label: 'Dusk' },
  { value: 'night', label: 'Night' },
];
