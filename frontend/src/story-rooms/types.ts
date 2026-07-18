/**
 * Types for the player-facing Story Rooms page (#2450 Fix 2 — spec Decision 1's
 * promised web surface for joining/leaving GM story rooms).
 *
 * Thin aliases over the generated schema (`GET /api/gm/my-story-grants/`, see
 * `world.gm.story_views.MyStoryGrantsViewSet` / `world.gm.serializers.MyStoryGrantSerializer`)
 * plus the join/leave action-key union this surface dispatches.
 */
import type { components } from '@/generated/api';

export type MyStoryGrant = components['schemas']['MyStoryGrant'];
export type PaginatedMyStoryGrantList = components['schemas']['PaginatedMyStoryGrantList'];

/** Registry keys of the player-side story-room verbs (`actions/definitions/story_builder.py`). */
export type StoryRoomActionKey = 'join_story_room' | 'leave_story_room';
