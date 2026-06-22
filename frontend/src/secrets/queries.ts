/** React Query hooks for the secret tab (#1334). */
import { useQuery } from '@tanstack/react-query';

import { listKnownSecrets } from './api';

export const secretKeys = {
  known: (subjectId: number, viewerId: number) =>
    ['secrets', 'known', subjectId, viewerId] as const,
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
