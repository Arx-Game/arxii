/**
 * Almanach de Catenys API (#3983 Task 7): the staff house-builder reads plus
 * REGISTRY dispatch, following `world-builder/api.ts` line for line in shape
 * — `apiFetch`/`withQuery` for GET, `throwApiError` on a non-ok response,
 * and the shared `dispatchCanvasAction` for the ten REGISTRY actions Task 6
 * wired. Every route here is staff-only (`IsAdminUser`, `almanach_views.py`).
 */
import { apiFetch, withQuery } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';
import type { components } from '@/generated/api';

import type {
  AlmanachActionKey,
  HouseDocument,
  LadderMode,
  LadderPayload,
  PaginatedAlmanachHouseSummaryList,
  PaginatedAlmanachRealmList,
  PaginatedLandShapeList,
  RealmCharter,
} from './types';

export type Gender = components['schemas']['Gender'];

export type { DispatchResult };

async function getJson<T>(url: string, fallbackError: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) await throwApiError(res, fallbackError);
  return (await res.json()) as T;
}

export function fetchRealms(): Promise<PaginatedAlmanachRealmList> {
  return getJson('/api/almanach/realms/', 'Failed to load realms.');
}

/** `?for=staff|founder` — NOTE the wire param is `for`, not `mode`. */
export function fetchLadder(realmId: number, mode: LadderMode): Promise<LadderPayload> {
  const qs = new URLSearchParams({ for: mode }).toString();
  return getJson(
    withQuery(`/api/almanach/realms/${realmId}/ladder/`, qs),
    'Failed to load the ladder.'
  );
}

/**
 * `realmId` omitted lists every house in the game (`AlmanachHouseFilter.realm`
 * is an optional `?realm=` filter, `almanach_views.py`) — #3983 Task 9 needs
 * this for the House Document route, which carries no realm id of its own
 * (the document's `realm` section reports title/demesne facts, never a realm
 * identity): resolving a vassal's held-by name to a house link, and
 * populating the "swear a house"/"born into" pickers, have nothing to scope
 * a realm-filtered fetch to.
 */
export function fetchHouses(realmId?: number): Promise<PaginatedAlmanachHouseSummaryList> {
  if (realmId == null) return getJson('/api/almanach/houses/', 'Failed to load houses.');
  const qs = new URLSearchParams({ realm: String(realmId) }).toString();
  return getJson(withQuery('/api/almanach/houses/', qs), 'Failed to load houses.');
}

export function fetchHouseDocument(houseId: number): Promise<HouseDocument> {
  return getJson(`/api/almanach/houses/${houseId}/document/`, 'Failed to load the house document.');
}

export function fetchLandShapes(): Promise<PaginatedLandShapeList> {
  return getJson('/api/almanach/land-shapes/', 'Failed to load land shapes.');
}

/**
 * A realm's charter (#3983 Plan B Task 3): the tier-less template's default
 * succession law, the realm's blank-floor nobiliary particle, its House
 * chapter's Quiddity prompt, and its capital's name. Opened to any
 * authenticated player (Task 3), unlike the staff-only reads above — the
 * Founder Almanach's Seat/House chapters call it directly.
 */
export function fetchCharter(realmId: number): Promise<RealmCharter> {
  return getJson(`/api/almanach/realms/${realmId}/charter/`, 'Failed to load the realm charter.');
}

/**
 * The site-wide gender catalog (#3983 Task 9) — `almanach_edit_kin`'s
 * `gender_id` is a real FK (`Gender`, `character_sheets/models.py`), and the
 * only list endpoint for it today lives under character-creation
 * (`/api/character-creation/genders/`); it's a plain catalog read with no
 * CG-flow coupling, so the Almanach reuses it rather than growing a second
 * one. Not `PaginatedAlmanachHouseSummaryList`-style paginated — the
 * operation returns a bare array.
 */
export function fetchGenders(): Promise<Gender[]> {
  return getJson('/api/character-creation/genders/', 'Failed to load genders.');
}

/**
 * Dispatch a staff Almanach REGISTRY action (#3983 Task 6 keys) for
 * `characterId`. Thin wrapper pinning `AlmanachActionKey` over the shared
 * `dispatchCanvasAction` (`@/map-canvas/dispatch`) — same wire shape as
 * `dispatchWorldBuilder` (`@/world-builder/api`), different key union.
 */
export function dispatchAlmanach(
  characterId: number,
  key: AlmanachActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, key, kwargs);
}
