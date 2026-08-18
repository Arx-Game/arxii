/** React Query hooks for the secret tab (#1334), the grievance flow (#1429), and staff
 * authoring (#3266). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createAuthoredSecret,
  getAuthoredSecrets,
  getSecretCategories,
  gossipAction,
  listGossip,
  listGrievanceOptions,
  listKnownSecrets,
  submitGrievance,
  updateAuthoredSecret,
} from './api';
import type {
  AuthorSecretPayload,
  GossipActionPayload,
  SubmitGrievancePayload,
  UpdateAuthoredSecretPayload,
} from './api';

export const secretKeys = {
  knownAll: ['secrets', 'known'] as const,
  known: (subjectId: number, viewerId: number) =>
    [...secretKeys.knownAll, subjectId, viewerId] as const,
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
      queryClient.invalidateQueries({ queryKey: secretKeys.knownAll });
    },
  });
}

export const gossipKeys = {
  all: ['secrets', 'gossip'] as const,
  list: (viewerId: number) => [...gossipKeys.all, viewerId] as const,
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
      queryClient.invalidateQueries({ queryKey: gossipKeys.all });
    },
  });
}

export const authoredSecretKeys = {
  all: ['secrets', 'authored'] as const,
  bySubject: (subjectId: number) => [...authoredSecretKeys.all, subjectId] as const,
  categories: ['secrets', 'authored-categories'] as const,
};

/** Staff-only omniscient view of a character's authored secrets (#3266). */
export function useAuthoredSecretsQuery(subjectId: number) {
  return useQuery({
    queryKey: authoredSecretKeys.bySubject(subjectId),
    queryFn: () => getAuthoredSecrets(subjectId),
    enabled: Number.isFinite(subjectId),
  });
}

/** The staff-authored category catalog a secret's category select is fed by (#3266). */
export function useSecretCategoriesQuery() {
  return useQuery({
    queryKey: authoredSecretKeys.categories,
    queryFn: getSecretCategories,
  });
}

/** Staff-mint a new secret; refetches the subject's authored list on success (#3266). */
export function useCreateAuthoredSecretMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AuthorSecretPayload) => createAuthoredSecret(payload),
    onSuccess: (secret) => {
      queryClient.invalidateQueries({
        queryKey: authoredSecretKeys.bySubject(secret.subject_sheet),
      });
    },
  });
}

/** Staff-edit an authored secret; refetches the subject's authored list on success (#3266). */
export function useUpdateAuthoredSecretMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UpdateAuthoredSecretPayload }) =>
      updateAuthoredSecret(id, payload),
    onSuccess: (secret) => {
      queryClient.invalidateQueries({
        queryKey: authoredSecretKeys.bySubject(secret.subject_sheet),
      });
    },
  });
}
