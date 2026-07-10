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
  /**
   * `writeups()` (no arg) is the shared prefix used to invalidate every
   * subject-scoped variant at once; `writeups(subjectCharacterId)` is the
   * specific key a given sheet's query is cached under.
   */
  writeups: (subjectCharacterId?: number) =>
    subjectCharacterId == null
      ? ([...relationshipsKeys.all, 'writeups'] as const)
      : ([...relationshipsKeys.all, 'writeups', subjectCharacterId] as const),
};

/**
 * GET the caller's commendable writeups about one owned character
 * (tenure-scoped, SHARED/PUBLIC only).
 *
 * `subjectCharacterId` (the viewed CharacterSheet pk) is threaded into both
 * the request (`?subject_character=`) and the query key — required because
 * the endpoint is scoped to the requester's *account*, which may tenure-own
 * more than one character; without narrowing, a multi-character account's
 * Writeups subsection would show every owned character's writeups under
 * whichever sheet happens to be open (fix wave, Finding 2).
 *
 * Pass `enabled=false` when viewing a character sheet that is NOT the
 * caller's own — fetching it on a foreign sheet would return the *viewer's*
 * own writeups, not the viewed character's.
 */
export function useMyWriteups(subjectCharacterId?: number, enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.writeups(subjectCharacterId),
    queryFn: () => api.getMyWriteups(subjectCharacterId),
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
