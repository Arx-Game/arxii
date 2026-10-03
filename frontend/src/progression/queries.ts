/**
 * React Query hooks for progression data.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  claimKudosForXP,
  conveneDurance,
  fetchAccountProgression,
  fetchCharacterXpLedger,
  fetchDuranceStatus,
  fetchProgressionUnlocks,
  joinDuranceSession,
  purchaseProgressionUnlock,
} from './api';
import { useAccount } from '@/store/hooks';
import { speciesKeys } from '@/species/queries';
import type { PurchaseUnlockRequest } from './types';

export function useAccountProgressionQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['account-progression'],
    queryFn: fetchAccountProgression,
    enabled: !!account,
  });
}

export function useClaimKudosMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimCategoryId, amount }: { claimCategoryId: number; amount: number }) =>
      claimKudosForXP(claimCategoryId, amount),
    onSuccess: (data) => {
      queryClient.setQueryData(['account-progression'], data);
    },
  });
}

// ---------------------------------------------------------------------------
// Unlock shop (#3045)
// ---------------------------------------------------------------------------

export type UnlockType =
  | 'class_level'
  | 'thread_xp_lock'
  | 'skill_breakthrough'
  | 'language_breakthrough';

export const progressionUnlocksKey = (unlockType?: UnlockType) => [
  'progression-unlocks',
  unlockType ?? 'all',
];

export function useProgressionUnlocksQuery(unlockType?: UnlockType) {
  const account = useAccount();
  return useQuery({
    queryKey: progressionUnlocksKey(unlockType),
    queryFn: () => fetchProgressionUnlocks(unlockType),
    enabled: !!account,
  });
}

export function usePurchaseUnlockMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PurchaseUnlockRequest) => purchaseProgressionUnlock(body),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['progression-unlocks'] });
      queryClient.invalidateQueries({ queryKey: ['account-progression'] });
      queryClient.invalidateQueries({ queryKey: ['durance-status'] });
      // A language breakthrough raises the trait rating the sheet's Languages
      // section reads — invalidate it too, or the sheet shows the stale,
      // still-locked rating until an unrelated refetch happens to run (#4090).
      if (variables.unlock_type === 'language_breakthrough') {
        queryClient.invalidateQueries({ queryKey: speciesKeys.myLanguages() });
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Durance readiness hub (#3045)
// ---------------------------------------------------------------------------

export function useDuranceStatusQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['durance-status'],
    queryFn: fetchDuranceStatus,
    enabled: !!account,
  });
}

export function useConveneDuranceMutation() {
  return useMutation({
    mutationFn: conveneDurance,
  });
}

export function useJoinDuranceSessionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sessionId,
      participantKwargs,
    }: {
      sessionId: number;
      participantKwargs: { testament: string; path_id?: number };
    }) => joinDuranceSession(sessionId, participantKwargs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['durance-status'] });
      queryClient.invalidateQueries({ queryKey: ['account-progression'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Per-character XP attribution (#3748)
// ---------------------------------------------------------------------------

/** What this character has earned and what has been spent on them. Owner-only. */
export function useCharacterXpLedgerQuery(sheetId: number) {
  return useQuery({
    queryKey: ['xp-ledger', sheetId],
    queryFn: () => fetchCharacterXpLedger(sheetId),
    enabled: !!sheetId,
  });
}
