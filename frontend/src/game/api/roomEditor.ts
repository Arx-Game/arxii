import { apiFetch } from '@/evennia_replacements/api';

export interface RoomEditInput {
  name?: string;
  description?: string;
  is_public?: boolean;
}

/**
 * Dispatch the `edit_room` REGISTRY action for `characterId`, editing the room
 * the character is currently standing in (#1470). Owner-gated server-side.
 *
 * Returns the action's human-readable result message (e.g. "Room updated." or
 * the reason an edit was refused). Throws on a dispatch-level error (4xx) with
 * the server's `detail`.
 */
export async function editRoom(characterId: number, input: RoomEditInput): Promise<string> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: { backend: 'registry', registry_key: 'edit_room' },
      kwargs: input,
    }),
  });
  if (!res.ok) {
    let detail = 'Failed to update the room.';
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
  const data = (await res.json()) as { message?: string | null };
  return data.message ?? 'Room updated.';
}
