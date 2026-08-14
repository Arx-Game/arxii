/**
 * Species React Query hooks (#2993).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchMyLanguages } from './api';

export const speciesKeys = {
  all: ['species'] as const,
  myLanguages: () => [...speciesKeys.all, 'my-languages'] as const,
};

/**
 * The viewer's own active character's known languages — backs both the
 * composer's `LanguageSelector` (#2993 Task 8) and the character sheet's
 * Languages section. Self-scoped server-side (no character param needed);
 * an account with no active character gets an empty array, never an error.
 */
export function useMyLanguages() {
  return useQuery({
    queryKey: speciesKeys.myLanguages(),
    queryFn: fetchMyLanguages,
  });
}
