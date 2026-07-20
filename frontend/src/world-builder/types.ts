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
  | 'staff_link_rooms'
  | 'staff_unlink_rooms'
  | 'staff_rename_exit'
  | 'staff_place_room'
  | 'staff_remove_room'
  | 'promote_room'
  | 'promote_area'
  | 'staff_place_clue'
  | 'staff_remove_clue'
  | 'staff_place_clue_trigger'
  | 'staff_remove_clue_trigger'
  | 'staff_place_portal_anchor'
  | 'staff_remove_portal_anchor';

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
