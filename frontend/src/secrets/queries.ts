/** React Query hooks for the secret tab (#1334). */
import { useQuery } from '@tanstack/react-query';

import { listKnownSecrets } from './api';

export const secretKeys = {
  known: (subjectId: number) => ['secrets', 'known', subjectId] as const,
};

export function useKnownSecretsQuery(subjectId: number) {
  return useQuery({
    queryKey: secretKeys.known(subjectId),
    queryFn: () => listKnownSecrets(subjectId),
    enabled: Number.isFinite(subjectId),
  });
}
