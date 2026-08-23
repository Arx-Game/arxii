/**
 * Boards API client (#3286) — player-postable bulletin boards.
 *
 * Reads hit the boards ViewSets directly; writes (post/edit/remove) dispatch
 * through the standard action seam (`useDispatchPlayerAction`, `@/combat/queries`)
 * — this module carries no POST/PATCH/DELETE of its own, matching the
 * travel/traps precedent (ADR-0001: writes always go through Actions).
 */

import { apiFetch } from '@/evennia_replacements/api';

export interface Board {
  id: number;
  room_profile: number | null;
  organization: number | null;
  name: string;
  max_active_posts: number;
  is_location_board: boolean;
  is_org_board: boolean;
}

export interface BoardPost {
  id: number;
  board: number;
  title: string;
  body: string;
  /** Per-viewer persona display — a masked poster's name shows the mask. */
  author_display: string;
  created_at: string;
  edited_at: string | null;
  is_removed: boolean;
}

interface Paginated<T> {
  results: T[];
}

/** GET /api/boards/boards/?room_profile={id} — the room's LOCATION board, or null. */
export async function fetchBoardForRoom(roomProfileId: number): Promise<Board | null> {
  const res = await apiFetch(`/api/boards/boards/?room_profile=${roomProfileId}`);
  if (!res.ok) throw new Error('Failed to load the room board');
  const data = (await res.json()) as Paginated<Board>;
  return data.results[0] ?? null;
}

/** GET /api/boards/boards/?organization={id} — the org's board, or null. */
export async function fetchBoardForOrg(organizationId: number): Promise<Board | null> {
  const res = await apiFetch(`/api/boards/boards/?organization=${organizationId}`);
  if (!res.ok) throw new Error('Failed to load the org board');
  const data = (await res.json()) as Paginated<Board>;
  return data.results[0] ?? null;
}

/** GET /api/boards/posts/?board={id} — active posts, newest first, display-capped server-side. */
export async function fetchBoardPosts(boardId: number): Promise<BoardPost[]> {
  const res = await apiFetch(`/api/boards/posts/?board=${boardId}&page_size=50`);
  if (!res.ok) throw new Error('Failed to load board posts');
  const data = (await res.json()) as Paginated<BoardPost>;
  return data.results;
}
