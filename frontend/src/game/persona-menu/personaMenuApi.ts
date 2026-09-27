import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type PersonaMenuData = components['schemas']['PersonaMenu'];
export type PersonaMenuItemData = components['schemas']['PersonaMenuItem'];

/** GET the persona menu (#4030): what this character can do to one persona, and why not. */
export async function fetchPersonaMenu(
  characterId: number,
  personaId: number
): Promise<PersonaMenuData> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/personas/${personaId}/menu/`);
  if (!res.ok) throw new Error('Failed to load the persona menu');
  return (await res.json()) as PersonaMenuData;
}

export function usePersonaMenuQuery(
  characterId: number | null,
  personaId: number,
  enabled: boolean
) {
  return useQuery({
    queryKey: ['persona-menu', characterId, personaId],
    queryFn: () => fetchPersonaMenu(characterId as number, personaId),
    enabled: enabled && characterId !== null && characterId > 0,
    staleTime: 5_000,
  });
}
