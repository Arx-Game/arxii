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
  | 'staff_remove_portal_anchor'
  | 'atlas_create_region_map'
  | 'atlas_carve_footprint'
  | 'atlas_paint_terrain';

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

/**
 * Mirrors `world.areas.constants.AreaLevel` (#4085): sizes only, a barony being the
 * actual holding of any shape (a city is one). Kept in step by
 * `__tests__/areaLevels.test.ts` against the generated API schema.
 */
export const AREA_LEVELS: { value: number; label: string }[] = [
  { value: 10, label: 'Building' },
  { value: 20, label: 'Neighborhood' },
  { value: 30, label: 'Ward' },
  { value: 40, label: 'Barony' },
  { value: 53, label: 'County' },
  { value: 56, label: 'Duchy' },
  { value: 60, label: 'Kingdom' },
  { value: 65, label: 'Empire' },
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

/** The world map (#4242): a region on the world grid of 10-mile pips. */
export interface RegionMapUploadSummary {
  id: number;
  file_name: string;
  byte_size: number;
  generator_version: string;
  source_width_px: number;
  source_height_px: number;
  uploaded_by_name: string;
  uploaded_at: string;
  rasterized_at: string | null;
}

export interface RegionMapSummary {
  id: number;
  name: string;
  area: number | null;
  area_name: string;
  anchor_x: number;
  anchor_y: number;
  width_cells: number;
  height_cells: number;
  pips_per_cell: number;
  created_at: string;
  latest_upload: RegionMapUploadSummary | null;
}

/** One pip row of the pips payload: `[x, y, terrain, river]`. */
export type RegionMapPipRow = [number, number, string, boolean];

export interface RegionMapFootprint {
  area_id: number;
  name: string;
  level: number;
  level_display: string;
  parent_id: number | null;
  realm_id: number | null;
  holder_org_id: number | null;
  holder_name: string;
  title_id: number | null;
  seat: [number, number] | null;
  pips: [number, number][];
}

export interface RegionMapPips {
  region: RegionMapSummary;
  terrains: string[];
  pips: RegionMapPipRow[];
  footprints: RegionMapFootprint[];
}

export interface RegionMapUploadResult {
  upload: RegionMapUploadSummary;
  pip_count: number;
  region: RegionMapSummary;
}
