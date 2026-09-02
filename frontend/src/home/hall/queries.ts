/**
 * The Hall (#3412 slice 2) — React Query hooks for surfaces with no existing
 * home. Invitation/offer *response* mutations and their list fetches mostly
 * live in their owning domains (`@/events/queries`, `@/societies/queries`)
 * and are re-exported/composed by the band components directly — this file
 * is only for what's genuinely new here: the clock, and (#3478 task 5) the
 * GM slot's mint/read/edit hooks.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchClockState, fetchGMProfileMine, mintGMCharacter, updateGMProfileMine } from './api';
import type { GMProfileMine } from './types';
import { useAccount } from '@/store/hooks';

// Re-exported so existing imports of the Hall's query module keep working
// (`useGMProfileMineQuery` below stays its own hook, own cache entry - see
// `@/gm/queries` for why).
export { useGMProfileMine, gmKeys } from '@/gm/queries';

export const hallKeys = {
  clock: ['hall', 'clock'] as const,
  gmProfileMine: ['hall', 'gm-profile-mine'] as const,
};

const ONE_MINUTE = 60 * 1000;

/** The World band's calendar plate. No `throwOnError` — a clock hiccup shouldn't blank the Hall. */
export function useClockQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: hallKeys.clock,
    queryFn: fetchClockState,
    enabled: !!account,
    staleTime: ONE_MINUTE,
  });
}

/**
 * The requesting account's own GM profile (#3478). `enabled` lets callers
 * gate the request on having a GM/Staff roster entry at all — a plain PC
 * account has nothing to fetch here. `retry: false` and no `throwOnError`:
 * a 404 (staff with no approved `GMProfile`) is an expected, silent
 * "nothing to edit" result for `GMSlot`, not a failure to surface or retry.
 */
export function useGMProfileMineQuery(enabled: boolean) {
  return useQuery({
    queryKey: hallKeys.gmProfileMine,
    queryFn: fetchGMProfileMine,
    enabled,
    retry: false,
  });
}

/**
 * Mint the account's GM/Staff character (`CreateGMCharacterDialog`).
 * Invalidates `['my-roster-entries']` (the new entry appears in the Hall's
 * character grid) and `['account']` (`is_gm`/`available_characters` may
 * change) on success — mirrors `useSelectCharacterMutation`'s invalidation
 * shape above.
 */
export function useMintGMCharacterMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => mintGMCharacter(name),
    onSuccess: (result) => {
      toast.success(`${result.name} created.`);
      queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
      queryClient.invalidateQueries({ queryKey: ['account'] });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : 'Failed to create the GM character.'),
  });
}

/** Save `contact_times`/`ooc_info` from `EditGMProfileDialog`. */
export function useUpdateGMProfileMineMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Pick<GMProfileMine, 'contact_times' | 'ooc_info'>>) =>
      updateGMProfileMine(data),
    onSuccess: () => {
      toast.success('GM profile saved.');
      queryClient.invalidateQueries({ queryKey: hallKeys.gmProfileMine });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : 'Failed to save your GM profile.'),
  });
}
