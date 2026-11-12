/**
 * IC missives (#3289). Reads hit the read-only `/api/missives/` viewset with the
 * tab's `?entry_id=` (per-tab identity); every write dispatches a REGISTRY action
 * for the acting character (`actions/definitions/missives.py`).
 */

import { apiFetch } from '@/evennia_replacements/api';
import { parseDispatchBody } from '@/lib/errors';
import type { PaginatedResponse } from '@/shared/types';
import type { Missive, MissiveActionKey } from './types';

const MISSIVES_URL = '/api/missives/';

export async function fetchMissives(
  entryId: number,
  page = 1
): Promise<PaginatedResponse<Missive>> {
  const res = await apiFetch(`${MISSIVES_URL}?entry_id=${entryId}&page=${page}`);
  if (!res.ok) throw new Error('Failed to load missives');
  return res.json() as Promise<PaginatedResponse<Missive>>;
}

export async function fetchMissiveUnreadCount(entryId: number): Promise<number> {
  const res = await apiFetch(`${MISSIVES_URL}unread-count/?entry_id=${entryId}`);
  if (!res.ok) throw new Error('Failed to load unread missives');
  const data = (await res.json()) as { count: number };
  return data.count;
}

export async function dispatchMissiveAction(
  characterId: number,
  key: MissiveActionKey,
  kwargs: Record<string, unknown>
): Promise<{ message: string; data: Record<string, unknown> | undefined }> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: { backend: 'registry', registry_key: key }, kwargs }),
  });
  const { success, message, data } = await parseDispatchBody(res);
  if (!res.ok || success === false) throw new Error(message ?? 'The missive did not go.');
  return { message: message ?? '', data };
}
