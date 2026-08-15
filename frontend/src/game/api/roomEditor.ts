import { apiFetch } from '@/evennia_replacements/api';
import { parseDispatchBody } from '@/lib/errors';

export interface RoomEditInput {
  name?: string;
  description?: string;
  is_public?: boolean;
}

/**
 * Dispatch the `edit_room` REGISTRY action for `characterId`, editing the room
 * the character is currently standing in (#1470). Owner-gated server-side.
 *
 * Returns the action's human-readable result message (e.g. "Room updated.").
 * Throws on a dispatch-level error (4xx) OR a business-rule rejection —
 * `DispatchActionView` resolves HTTP 200 even for a refused edit, so
 * `success === false` (not `res.ok` alone) is the signal an edit was refused
 * (#3155).
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
  const { success, message } = await parseDispatchBody(res);
  if (!res.ok || success === false) throw new Error(message ?? 'Failed to update the room.');
  return message ?? 'Room updated.';
}
