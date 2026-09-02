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
import { fetchGMProfileMine } from '@/home/hall/api';

export const gmKeys = {
  profileMine: ['gm', 'profile-mine'] as const,
};

const FIVE_MINUTES = 5 * 60 * 1000;

/** The requesting account's own GM profile, or `null` when it has none (404). */
export function useGMProfileMine() {
  return useQuery({
    queryKey: gmKeys.profileMine,
    queryFn: fetchGMProfileMine,
    staleTime: FIVE_MINUTES,
  });
}
