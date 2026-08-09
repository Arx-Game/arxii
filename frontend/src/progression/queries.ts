/**
 * React Query hooks for progression data.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  claimKudosForXP,
  conveneDurance,
  fetchAccountProgression,
  fetchDuranceStatus,
  fetchProgressionUnlocks,
  joinDuranceSession,
  purchaseProgressionUnlock,
} from './api';
import { useAccount } from '@/store/hooks';
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

export const progressionUnlocksKey = (
  unlockType?: 'class_level' | 'thread_xp_lock' | 'skill_breakthrough'
) => ['progression-unlocks', unlockType ?? 'all'];

export function useProgressionUnlocksQuery(
  unlockType?: 'class_level' | 'thread_xp_lock' | 'skill_breakthrough'
) {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['progression-unlocks'] });
      queryClient.invalidateQueries({ queryKey: ['account-progression'] });
      queryClient.invalidateQueries({ queryKey: ['durance-status'] });
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
