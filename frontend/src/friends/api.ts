/** OOC friends-list REST calls (#1727). */
import { apiFetch } from '@/evennia_replacements/api';

import type { PaginatedFriendshipList } from './types';

/** The requesting player's friendships (across all their characters). */
export async function listFriends(): Promise<PaginatedFriendshipList> {
  const res = await apiFetch('/api/scenes/friends/');
  if (!res.ok) {
    throw new Error('Failed to load friends');
  }
  return res.json() as Promise<PaginatedFriendshipList>;
}

export interface AddFriendPayload {
  /** Your friending character (a RosterEntry pk). */
  viewer: number;
  /** The character to friend (a RosterEntry pk). */
  friend: number;
  /** Friend them from ALL your characters (fan-out) rather than just `viewer`. */
  allCharacters?: boolean;
}

/** Add a friend — from one character or all of yours (#1727). */
export async function addFriend(payload: AddFriendPayload): Promise<void> {
  const res = await apiFetch('/api/scenes/friends/', {
    method: 'POST',
    body: JSON.stringify({
      viewer: payload.viewer,
      friend: payload.friend,
      all_characters: payload.allCharacters ?? false,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Failed to add friend');
  }
}

/** Remove one friendship row (per-character). */
export async function removeFriend(id: number): Promise<void> {
  const res = await apiFetch(`/api/scenes/friends/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to remove friend');
  }
}
