/**
 * Character sheet React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchCharacterSheet } from './api';

/** The rich character-sheet payload for a single character (sheet id == character id). */
export function useCharacterSheetQuery(sheetId: number) {
  return useQuery({
    queryKey: ['character-sheets', sheetId],
    queryFn: () => fetchCharacterSheet(sheetId),
    enabled: !!sheetId,
  });
}
