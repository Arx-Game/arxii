/**
 * Room-features API client (#3011) — the player-facing trap read surface.
 *
 * Reads `GET /api/room-features/traps/?character_id=` — armed traps the given
 * character can currently see in their own room (not-hidden, or already in
 * that character's own `detected_by`; see `RoomTrapViewSet` for the full leak
 * table). Not paginated — a room's trap count is naturally small (unlike
 * `fetchPortalDestinations`'s paginated network-wide anchor list), so this
 * reads a plain array.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type RoomTrap = components['schemas']['Trap'];

/** Fetch the armed traps visible to `characterId` in their current room. */
export async function fetchRoomTraps(characterId: number): Promise<RoomTrap[]> {
  const res = await apiFetch(`/api/room-features/traps/?character_id=${characterId}`);
  if (!res.ok) throw new Error('Failed to load room traps');
  return (await res.json()) as RoomTrap[];
}
