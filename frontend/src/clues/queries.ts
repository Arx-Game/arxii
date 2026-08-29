/**
 * Clues React Query hooks (#1575, #3432).
 */

import { useMutation, useQuery } from '@tanstack/react-query';

import { authorClue, fetchHeldClues } from './api';

/** The held clues for one of the requester's characters (the journal). */
export function useHeldClues(characterSheetId: number) {
  return useQuery({
    queryKey: ['clues', 'held', characterSheetId],
    queryFn: () => fetchHeldClues(characterSheetId),
  });
}

/** Dispatch `author_clue` (#3432) as `characterId`. See `AuthorClueDialog`. */
export function useAuthorClueMutation(characterId: number) {
  return useMutation({
    mutationFn: (kwargs: Record<string, unknown>) => authorClue(characterId, kwargs),
  });
}
