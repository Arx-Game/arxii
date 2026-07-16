/** OOC friends-list (#1727) + rivalry-declaration (#2170) REST calls. */
import { apiFetch } from '@/evennia_replacements/api';

import type { PaginatedFriendshipList, PaginatedRivalryList, Rivalry } from './types';

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

/** The requesting player's rival declarations (across all their characters, #2170). */
export async function listRivals(): Promise<PaginatedRivalryList> {
  const res = await apiFetch('/api/scenes/rivals/');
  if (!res.ok) {
    throw new Error('Failed to load rivals');
  }
  return res.json() as Promise<PaginatedRivalryList>;
}

export interface DeclareRivalPayload {
  /** Your declaring character (a RosterEntry pk). */
  viewer: number;
  /** The character to declare a rival (a RosterEntry pk). */
  rival: number;
}

/** Declare a rival — one side of the #2170 double opt-in; mutual once they declare you back. */
export async function declareRival(payload: DeclareRivalPayload): Promise<Rivalry> {
  const res = await apiFetch('/api/scenes/rivals/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Failed to declare rival');
  }
  return res.json() as Promise<Rivalry>;
}

/** Withdraw one of your own rival declarations. */
export async function withdrawRival(id: number): Promise<void> {
  const res = await apiFetch(`/api/scenes/rivals/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to withdraw rival declaration');
  }
}
