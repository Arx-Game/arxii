import { apiFetch } from '@/evennia_replacements/api';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

import type { PaginatedMyStoryGrantList, StoryRoomActionKey } from './types';

export type { DispatchResult };

async function getJson<T>(url: string, fallbackError: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) {
    let detail = fallbackError;
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // body wasn't JSON; keep the generic message
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

/** The current account's own story-room access grants — see `world.gm.story_views`. */
export function fetchMyStoryGrants(): Promise<PaginatedMyStoryGrantList> {
  return getJson('/api/gm/my-story-grants/', 'Failed to load your story-room invitations.');
}

/**
 * Dispatch `join_story_room`/`leave_story_room` for `characterId` — the exact
 * character the grant was issued to (see `MyStoryGrantSerializer`'s
 * `character_id` doc comment for why it can't be "whichever character is
 * active"). Thin wrapper over the shared `dispatchCanvasAction`
 * (`@/map-canvas/dispatch`), same wire shape as `dispatchStoryBuilder`
 * (`frontend/src/story-builder/api.ts`), different key union.
 */
export function dispatchStoryRoomAction(
  characterId: number,
  registryKey: StoryRoomActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, registryKey, kwargs);
}
