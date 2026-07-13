/** React Query hooks for crossover invites (#2075). */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type {
  CrossoverInviteAcceptBody,
  CrossoverInviteCreateBody,
  ListCrossoverInvitesParams,
} from './types';

// Re-export for convenience
export { getStakesSummary } from './api';
export type { StakesSummary } from './api';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const crossoverKeys = {
  all: ['crossover'] as const,
  invites: (params?: ListCrossoverInvitesParams) =>
    [...crossoverKeys.all, 'invites', params] as const,
  episodeScenes: (sceneId: number) =>
    [...crossoverKeys.all, 'episode-scenes', 'scene', sceneId] as const,
};

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useCrossoverInvites(params?: ListCrossoverInvitesParams) {
  return useQuery({
    queryKey: crossoverKeys.invites(params),
    queryFn: () => api.listCrossoverInvites(params),
    throwOnError: false,
  });
}

export function useEpisodeScenesForScene(sceneId: number | null | undefined) {
  return useQuery({
    queryKey: crossoverKeys.episodeScenes(sceneId ?? 0),
    queryFn: () => api.listEpisodeScenesForScene(sceneId!),
    enabled: sceneId != null && sceneId > 0,
    throwOnError: false,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreateCrossoverInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CrossoverInviteCreateBody) => api.createCrossoverInvite(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crossoverKeys.all }).catch(() => {});
    },
  });
}

export function useAcceptCrossoverInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & CrossoverInviteAcceptBody) =>
      api.acceptCrossoverInvite(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crossoverKeys.all }).catch(() => {});
    },
  });
}

export function useDeclineCrossoverInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, responseNote }: { id: number; responseNote?: string }) =>
      api.declineCrossoverInvite(id, responseNote),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crossoverKeys.all }).catch(() => {});
    },
  });
}

export function useWithdrawCrossoverInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.withdrawCrossoverInvite(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crossoverKeys.all }).catch(() => {});
    },
  });
}
