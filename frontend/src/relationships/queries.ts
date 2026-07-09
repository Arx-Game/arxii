/**
 * React Query hooks for the relationships module (#2031).
 *
 * Currently covers the writeups-commend surface only. Follows the same
 * key-factory + hook shape as frontend/src/magic/queries.ts.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type { GiveWriteupKudosRequest } from './api';

export const relationshipsKeys = {
  all: ['relationships'] as const,
  writeups: () => [...relationshipsKeys.all, 'writeups'] as const,
};

/**
 * GET the caller's commendable writeups (subject-scoped, SHARED/PUBLIC only).
 *
 * Pass `enabled=false` when viewing a character sheet that is NOT the
 * caller's own — the endpoint is requester-scoped (subject = the
 * authenticated user), so fetching it while viewing another character's
 * sheet would return the *viewer's* writeups, not the viewed character's.
 */
export function useMyWriteups(enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.writeups(),
    queryFn: api.getMyWriteups,
    enabled,
  });
}

/**
 * Commend a relationship writeup. Invalidates the writeups list so
 * kudos_count/viewer_has_kudosed refresh on success.
 */
export function useGiveWriteupKudos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GiveWriteupKudosRequest) => api.giveWriteupKudos(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: relationshipsKeys.writeups() }).catch(() => {});
    },
  });
}
