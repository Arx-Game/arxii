import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import type { FatigueStatus } from '@/fatigue/fatigueQueries';

export type CharacterStatus = components['schemas']['CharacterVitalsStatusEnum'];

export type CharacterVitalsData = Omit<components['schemas']['CharacterVitals'], 'fatigue'> & {
  // Generated VitalsFatigue types zone as plain string; FatigueStatus keeps the
  // FatigueZone union that FatigueBars' Record lookups depend on.
  fatigue: FatigueStatus;
};

/**
 * Fetch the vitals panel payload for a character (CharacterSheet pk).
 * Returns null on 401/403/404 — viewers without permission simply see no panel.
 */
export async function fetchCharacterVitals(
  characterId: number
): Promise<CharacterVitalsData | null> {
  const res = await apiFetch(`/api/vitals/${characterId}/`);
  if (res.status === 401 || res.status === 403 || res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load vitals for character ${characterId}`);
  return res.json();
}

export function useCharacterVitalsQuery(characterId: number) {
  return useQuery<CharacterVitalsData | null>({
    queryKey: ['character-vitals', characterId],
    queryFn: () => fetchCharacterVitals(characterId),
    enabled: characterId > 0,
    staleTime: 10_000,
  });
}
