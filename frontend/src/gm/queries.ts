/**
 * Shared GM-facing hooks with no other natural home (#3562 Task 5).
 *
 * `useGMProfileMine` wraps the same `GET /api/gm/profiles/mine/` fetcher the
 * Hall's GM slot already uses (`home/hall/api.ts`'s `fetchGMProfileMine`,
 * which resolves a 404 to `null` rather than throwing) but under its own
 * query key and always-enabled/long-staleTime shape: beat-authoring UI
 * (`BeatFormDialog`'s risk cap, `ConsequencePoolPicker`) reads this on
 * mount regardless of whether the account has an existing roster entry, and
 * `max_beat_risk`/`allow_custom_stakes` change rarely enough that a 5-minute
 * staleTime avoids a redundant refetch per dialog open.
 * `home/hall/queries.ts` re-exports this hook so existing imports of the
 * Hall's query module keep working; its own `useGMProfileMineQuery(enabled)`
 * stays separate (own cache entry, `retry: false`, caller-gated `enabled`)
 * since `GMSlot`/`EditGMProfileDialog` only want to fetch once a GM/Staff
 * roster entry exists.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import { throwApiError } from '@/lib/errors';
import { fetchGMProfileMine } from '@/home/hall/api';

export const gmKeys = {
  profileMine: ['gm', 'profile-mine'] as const,
  /** Everything waiting on the GM (#4188): the header badge and the Dashboard strip. */
  attention: ['gm-attention'] as const,
};

const FIVE_MINUTES = 5 * 60 * 1000;

/** How often the GMing badge re-reads the server, the Staff badge's cadence. */
const ATTENTION_REFETCH_MS = 60_000;

export type GMAttention = components['schemas']['GMAttention'];

/** GET /api/gm/attention/: the counts of what waits on this GM, plus `total`. */
export async function fetchGMAttention(): Promise<GMAttention> {
  const res = await apiFetch('/api/gm/attention/');
  if (!res.ok) await throwApiError(res, 'Failed to load what is waiting on you.');
  return (await res.json()) as GMAttention;
}

/**
 * What is waiting on the GM (#4188). One query feeds the GMing trigger's
 * badge (`total`) and the Dashboard's "Waiting on you" strip (the rows), so
 * the two can never disagree (ADR-4188). `enabled` is the account's `is_gm`:
 * the endpoint 403s an account with no GMProfile, so nothing asks for it.
 */
export function useGMAttention(enabled: boolean) {
  return useQuery({
    queryKey: gmKeys.attention,
    queryFn: fetchGMAttention,
    refetchInterval: ATTENTION_REFETCH_MS,
    enabled,
  });
}

/** The requesting account's own GM profile, or `null` when it has none (404). */
export function useGMProfileMine() {
  return useQuery({
    queryKey: gmKeys.profileMine,
    queryFn: fetchGMProfileMine,
    staleTime: FIVE_MINUTES,
  });
}
