/**
 * Types for the GM story-builder canvas (#2450) — thin aliases over the
 * generated schema plus the Task 5-7 action-key union.
 *
 * The area/room/exit read payloads were byte-for-byte the staff world-builder
 * shapes (`GET /api/gm/story-areas/.../manager/` reuses `area_manager_payload`,
 * see Task 9's report). Fix round 1 (#2450 Task 10 follow-up) added a
 * `grants` field to the manager's rooms and to `StoryInstance` — server-side
 * `StoryAreaManagerSerializer`/`StoryRoomSerializer` subclass the staff
 * serializers rather than changing them, so the manager payload now has its
 * own `StoryAreaManager`/`StoryRoom` schema components distinct from
 * `WorldBuilderAreaManager`/`WorldBuilderRoom`. Kept as a distinct module
 * (not a re-export from `@/world-builder/types`) so this surface can diverge
 * independently if the two payloads ever do.
 */
import type { components } from '@/generated/api';

export type StoryArea = components['schemas']['WorldBuilderArea'];
export type StoryAreaManager = components['schemas']['StoryAreaManager'];
export type StoryRoom = components['schemas']['StoryRoom'];
export type StoryExit = components['schemas']['WorldBuilderExit'];
export type PaginatedStoryAreaList = components['schemas']['PaginatedWorldBuilderAreaList'];
/** A GM's own active temp scene rooms — a bare array, not paginated (see `api.ts`). */
export type StoryInstance = components['schemas']['StoryInstance'];

/** Registry keys of the GM story-builder actions this surface dispatches (#2450 Tasks 5-7). */
export type StoryBuilderActionKey =
  | 'create_story_area'
  | 'edit_story_area'
  | 'remove_story_area'
  | 'story_dig_room'
  | 'story_edit_room'
  | 'story_link_rooms'
  | 'story_unlink_rooms'
  | 'story_place_room'
  | 'story_remove_room'
  | 'grant_story_room'
  | 'revoke_story_room'
  | 'spin_up_scene_room'
  | 'close_scene_room';
