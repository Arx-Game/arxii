/**
 * Player-facing NPC interaction client (#930): start / resolve / end against
 * the InteractionViewSet state machine. One interaction in flight per session
 * (the backend enforces it with a 409).
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { components } from '@/generated/api';

export type InteractionState = components['schemas']['InteractionState'];
export type InteractionOffer = components['schemas']['InteractionOffer'];

const BASE = '/api/npc-services/interactions';

async function post<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) await throwApiError(res, 'The interaction failed.');
  return (await res.json()) as T;
}

/**
 * Fold the tab's browsing identity (#3479) into a request body. These
 * endpoints take `entry_id` in the BODY (unlike missions' query param).
 * Null/undefined omits the field entirely, so the server falls back to the
 * account's durable selection.
 */
function withEntryId(
  body: Record<string, unknown>,
  entryId: number | null | undefined
): Record<string, unknown> {
  return entryId != null ? { ...body, entry_id: entryId } : body;
}

export function startInteraction(
  roleId: number,
  entryId?: number | null
): Promise<InteractionState> {
  return post(`${BASE}/start/`, withEntryId({ role_id: roleId }, entryId));
}

export function resolveOffer(offerId: number, entryId?: number | null): Promise<InteractionState> {
  return post(`${BASE}/resolve/`, withEntryId({ offer_id: offerId }, entryId));
}

export function endInteraction(entryId?: number | null): Promise<InteractionState> {
  return post(`${BASE}/end/`, withEntryId({}, entryId));
}
