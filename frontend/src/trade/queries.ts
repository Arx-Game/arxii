/**
 * Player<->player negotiated trade React Query hooks (#2990).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';

export const tradeKeys = {
  all: ['trade-sessions'] as const,
  list: () => [...tradeKeys.all, 'list'] as const,
  detail: (sessionId: number) => [...tradeKeys.all, 'detail', sessionId] as const,
};

/** The viewer's own open + past trade sessions. */
export function useTradeSessions() {
  return useQuery({ queryKey: tradeKeys.list(), queryFn: api.getTradeSessions });
}

/** One trade session; polls while it's still negotiable so both sides see live updates. */
export function useTradeSession(sessionId: number | null) {
  return useQuery({
    queryKey: tradeKeys.detail(sessionId ?? -1),
    queryFn: () => api.getTradeSession(sessionId as number),
    enabled: sessionId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'proposed' || status === 'active' ? 3000 : false;
    },
  });
}

function useInvalidateTrade(sessionId: number) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: tradeKeys.detail(sessionId) }).catch(() => {});
    qc.invalidateQueries({ queryKey: tradeKeys.list() }).catch(() => {});
  };
}

export function useProposeTrade(actorCharacterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetCharacterId: number) =>
      api.proposeTrade(actorCharacterId, targetCharacterId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tradeKeys.list() }).catch(() => {});
    },
  });
}

export function useAcceptTrade(actorCharacterId: number, sessionId: number) {
  const invalidate = useInvalidateTrade(sessionId);
  return useMutation({
    mutationFn: () => api.acceptTrade(actorCharacterId, sessionId),
    onSuccess: invalidate,
  });
}

export function useStageTradeItem(actorCharacterId: number, sessionId: number) {
  const invalidate = useInvalidateTrade(sessionId);
  return useMutation({
    mutationFn: (itemGameObjectId: number) =>
      api.stageTradeItem(actorCharacterId, sessionId, itemGameObjectId),
    onSuccess: invalidate,
  });
}

export function useUnstageTradeItem(actorCharacterId: number, sessionId: number) {
  const invalidate = useInvalidateTrade(sessionId);
  return useMutation({
    mutationFn: (stakeId: number) => api.unstageTradeItem(actorCharacterId, stakeId),
    onSuccess: invalidate,
  });
}

export function useSetTradeCoin(actorCharacterId: number, sessionId: number) {
  const invalidate = useInvalidateTrade(sessionId);
  return useMutation({
    mutationFn: (amount: number) => api.setTradeCoin(actorCharacterId, sessionId, amount),
    onSuccess: invalidate,
  });
}

export function useConfirmTrade(actorCharacterId: number, sessionId: number) {
  const invalidate = useInvalidateTrade(sessionId);
  return useMutation({
    mutationFn: () => api.confirmTrade(actorCharacterId, sessionId),
    onSuccess: invalidate,
  });
}

export function useCancelTrade(actorCharacterId: number, sessionId: number) {
  const invalidate = useInvalidateTrade(sessionId);
  return useMutation({
    mutationFn: () => api.cancelTrade(actorCharacterId, sessionId),
    onSuccess: invalidate,
  });
}
