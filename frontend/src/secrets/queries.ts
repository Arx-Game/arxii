/** React Query hooks for the secret tab (#1334) + the grievance flow (#1429). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { listGrievanceOptions, listKnownSecrets, submitGrievance } from './api';
import type { SubmitGrievancePayload } from './api';

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
