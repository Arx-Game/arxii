/**
 * Achievements React Query hooks (#1522).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchCharacterTitles } from './api';

/**
 * A character's earned, displayable titles. Keyed by CharacterSheet pk (== character ObjectDB pk).
 */
export function useCharacterTitles(characterSheetId: number) {
  return useQuery({
    queryKey: ['achievements', 'character-titles', characterSheetId],
    queryFn: () => fetchCharacterTitles(characterSheetId),
  });
}
