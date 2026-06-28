/**
 * Clues React Query hooks (#1575).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchHeldClues } from './api';

/** The held clues for one of the requester's characters (the journal). */
export function useHeldClues(characterSheetId: number) {
  return useQuery({
    queryKey: ['clues', 'held', characterSheetId],
    queryFn: () => fetchHeldClues(characterSheetId),
  });
}
