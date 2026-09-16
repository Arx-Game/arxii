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
import type { Prayer, Vision, VisionCreate } from './types';

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
