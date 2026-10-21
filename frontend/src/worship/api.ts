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
import type {
  HolySite,
  InvocationOptions,
  Pledge,
  PledgeCard,
  Prayer,
  ServiceTerms,
  Vision,
  VisionCreate,
} from './types';

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

function entryQuery(entryId?: number | null): string {
  return entryId != null ? `?entry_id=${entryId}` : '';
}

/** GET /api/worship/pledges/?being={id} (#4333): the pledge types a being offers. */
export async function fetchPledges(beingId: number): Promise<Pledge[]> {
  const res = await apiFetch(`/api/worship/pledges/?being=${beingId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the pledges.');
  return unwrap((await res.json()) as Paginated<Pledge> | Pledge[]);
}

/**
 * GET /api/worship/beings/{id}/service-terms/ (#4333): what earns favor with the being for a
 * character, and their earning rate. System-generated. `sheetId` names a sheet the requester
 * plays (the sheet page); otherwise the character this tab acts as (`entryId`) answers.
 */
export async function fetchServiceTerms(
  beingId: number,
  { sheetId, entryId }: { sheetId?: number | null; entryId?: number | null } = {}
): Promise<ServiceTerms> {
  const query = sheetId != null ? `?character_sheet=${sheetId}` : entryQuery(entryId);
  const res = await apiFetch(`/api/worship/beings/${beingId}/service-terms/${query}`);
  if (!res.ok) await throwApiError(res, 'Failed to load what earns favor.');
  return (await res.json()) as ServiceTerms;
}

/** GET /api/worship/beings/holy-site/ (#4333): the beings holy where the character stands. */
export async function fetchHolySites(entryId?: number | null): Promise<HolySite[]> {
  const res = await apiFetch(`/api/worship/beings/holy-site/${entryQuery(entryId)}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the holy site here.');
  return (await res.json()) as HolySite[];
}

/** GET /api/worship/pledge-cards/?character_sheet={sheetId} (#4333): newest first. */
export async function fetchPledgeCards(sheetId: number): Promise<PledgeCard[]> {
  const res = await apiFetch(`/api/worship/pledge-cards/?character_sheet=${sheetId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the pledge.');
  return unwrap((await res.json()) as Paginated<PledgeCard> | PledgeCard[]);
}

/** Dispatch `pledge_take` as `characterId`: `{ pledge: id, prayer }`. */
export function takePledge(
  characterId: number,
  pledge: number,
  prayer: string
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, 'pledge_take', { pledge, prayer });
}

/** Dispatch `pledge_close` as `characterId`: perform the open pledge's closing rite, giving
 * up `itemIds` (#4530) during it: their meaning eases the rite's roll. */
export function closePledge(characterId: number, itemIds: number[] = []): Promise<DispatchResult> {
  return dispatchCanvasAction(
    characterId,
    'pledge_close',
    itemIds.length > 0 ? { item_ids: itemIds } : {}
  );
}

/** Dispatch `sacrifice` as `characterId`: `{ item_ids, being? }`. */
export function sacrifice(
  characterId: number,
  itemIds: number[],
  being?: number | null
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, 'sacrifice', {
    item_ids: itemIds,
    ...(being != null ? { being } : {}),
  });
}
