/**
 * Achievements React Query hooks (#1522).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchPersonaTitles } from './api';

/**
 * A persona's earned, displayable titles (#3466). Keyed by Persona pk, not CharacterSheet pk —
 * titles are scoped to the face that earned them (a mask's deed never surfaces under the
 * primary persona). `personaId` is nullable so callers can render before it's resolved
 * (e.g. a foreign character sheet still loading its persona payload); the query stays
 * disabled until it is known.
 */
export function usePersonaTitles(personaId: number | null | undefined) {
  return useQuery({
    queryKey: ['achievements', 'persona-titles', personaId],
    queryFn: () => fetchPersonaTitles(personaId as number),
    enabled: personaId != null,
  });
}
