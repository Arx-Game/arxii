/**
 * Worship API client (#3779) — prayers and visions.
 *
 * Both lists are IC knowledge: the server scopes them to the characters the requesting
 * account plays, and to everyone for staff. Praying is an action (`pray`), dispatched through
 * the shared REGISTRY seam as the character; sending a vision is a staff POST.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';
import type { InvocationOptions, Prayer, Vision, VisionCreate } from './types';

interface Paginated<T> {
  results: T[];
}

function unwrap<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

/** GET /api/worship/visions/?recipient={sheetId} — newest first. */
export async function fetchVisions(recipientSheetId: number): Promise<Vision[]> {
  const res = await apiFetch(`/api/worship/visions/?recipient=${recipientSheetId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load visions.');
  return unwrap((await res.json()) as Paginated<Vision> | Vision[]);
}

/** GET /api/worship/prayers/?character_sheet={sheetId} — newest first. */
export async function fetchPrayers(sheetId: number): Promise<Prayer[]> {
  const res = await apiFetch(`/api/worship/prayers/?character_sheet=${sheetId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load prayers.');
  return unwrap((await res.json()) as Paginated<Prayer> | Prayer[]);
}

/** POST /api/worship/visions/ (staff): the service spends the being's pool and delivers. */
export async function sendVision(payload: VisionCreate): Promise<Vision> {
  const res = await apiFetch('/api/worship/visions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, 'The vision could not be sent.');
  return (await res.json()) as Vision;
}

/** Dispatch `pray` as `characterId`: `{ being: id, text }`. */
export function pray(characterId: number, being: number, text: string): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, 'pray', { being, text });
}

/**
 * GET /api/worship/beings/invocation-options/ (#4333) — the Call on favor picker for the
 * character this tab acts as: each being they hold a standing with, whether it can be invoked
 * now (and why not), uses left this week, the difficulty with each ease, and the bonus by result.
 */
export async function fetchInvocationOptions(entryId?: number | null): Promise<InvocationOptions> {
  const query = entryId != null ? `?entry_id=${entryId}` : '';
  const res = await apiFetch(`/api/worship/beings/invocation-options/${query}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the beings you can call on.');
  return (await res.json()) as InvocationOptions;
}
