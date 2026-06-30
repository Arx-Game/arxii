/** React Query hooks for the secret tab (#1334) + the grievance flow (#1429). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  gossipAction,
  listGossip,
  listGrievanceOptions,
  listKnownSecrets,
  submitGrievance,
} from './api';
import type { GossipActionPayload, SubmitGrievancePayload } from './api';

export const secretKeys = {
  known: (subjectId: number, viewerId: number) =>
    ['secrets', 'known', subjectId, viewerId] as const,
  grievanceOptions: ['secrets', 'grievance-options'] as const,
};

/** Secrets the active viewing character (`viewerId`) knows about `subjectId`. Disabled until
 * there's an active character — IC knowledge is per character, never account-wide. */
export function useKnownSecretsQuery(subjectId: number, viewerId: number | null) {
  return useQuery({
    queryKey: secretKeys.known(subjectId, viewerId ?? 0),
    queryFn: () => listKnownSecrets(subjectId, viewerId as number),
    enabled: Number.isFinite(subjectId) && viewerId != null,
  });
}

/** The preset grievance responses a wronged character may choose (#1429). */
export function useGrievanceOptionsQuery() {
  return useQuery({
    queryKey: secretKeys.grievanceOptions,
    queryFn: listGrievanceOptions,
  });
}

/** Register the active character's grievance against a secret's subject (#1429). */
export function useSubmitGrievanceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SubmitGrievancePayload) => submitGrievance(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['secrets', 'known'] });
    },
  });
}

export const gossipKeys = {
  list: (viewerId: number) => ['secrets', 'gossip', viewerId] as const,
};

/** The active character's spreadable gossip + regional heat. Disabled until there's an active
 * character — gossip is per character (and location-bound), never account-wide (#1572). */
export function useGossipQuery(viewerId: number | null) {
  return useQuery({
    queryKey: gossipKeys.list(viewerId ?? 0),
    queryFn: () => listGossip(viewerId as number),
    enabled: viewerId != null,
  });
}

/** Plant / seek / suppress gossip; refetches the list on success (#1572). */
export function useGossipActionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: GossipActionPayload) => gossipAction(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['secrets', 'gossip'] });
    },
  });
}
