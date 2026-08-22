/**
 * REST reads for scene check invocation (#3295): the player self-check picker
 * and the GM call-for-check prompt inbox. Answer/decline/self-check/call/propose
 * themselves are REGISTRY action dispatches (`useDispatchPlayerAction`), not
 * plain POSTs here — mirrors `@/gm-adjudication/api.ts`'s split.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { CheckCallTargetEntry, PlayerCheckTypeEntry } from './types';

async function throwOnBadResponse(res: Response, fallbackMessage: string): Promise<void> {
  if (res.ok) return;
  throw new Error(fallbackMessage);
}

/**
 * The player-facing check catalog browse (GET /api/checks/player-check-types/).
 * `characterId`, when given, additionally surfaces that character's own
 * synthesized magic CheckType row (never another character's).
 */
export async function getPlayerCheckTypeCatalog(
  search?: string,
  characterId?: number | null
): Promise<PlayerCheckTypeEntry[]> {
  const params = new URLSearchParams({ page_size: '50' });
  if (search) params.set('search', search);
  if (characterId != null) params.set('character_id', String(characterId));
  const res = await apiFetch(`/api/checks/player-check-types/?${params.toString()}`);
  await throwOnBadResponse(res, 'Failed to load the check catalog');
  const data = (await res.json()) as { results?: PlayerCheckTypeEntry[] };
  return data.results ?? [];
}

/**
 * The requesting player's pending `CheckCall` prompt(s) (#3295).
 * GET /api/checks/check-call-targets/ — bare array, `pagination_class = None`.
 */
export async function fetchMyCheckCalls(): Promise<CheckCallTargetEntry[]> {
  const res = await apiFetch('/api/checks/check-call-targets/');
  await throwOnBadResponse(res, 'Failed to load pending check calls');
  return (await res.json()) as CheckCallTargetEntry[];
}
