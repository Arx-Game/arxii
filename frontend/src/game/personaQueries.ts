import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/evennia_replacements/api';

export type PersonaType = 'primary' | 'established' | 'temporary';

/** A face a character can present as, for the top-bar switcher. */
export interface SwitchablePersona {
  id: number;
  name: string;
  persona_type: PersonaType;
  is_fake_name: boolean;
  thumbnail_url: string | null;
  thumbnail_media_url: string | null;
}

const personaKeys = {
  forCharacterSheet: (characterSheetId: number) =>
    ['character-personas', characterSheetId] as const,
};

async function fetchCharacterPersonas(characterSheetId: number): Promise<SwitchablePersona[]> {
  const res = await apiFetch(`/api/personas/?character_sheet=${characterSheetId}&page_size=100`);
  if (!res.ok) {
    throw new Error('Failed to load personas.');
  }
  const data = (await res.json()) as {
    results?: Array<{
      id: number;
      name: string;
      persona_type?: PersonaType;
      is_fake_name?: boolean;
      thumbnail_url?: string | null;
      thumbnail_media_url?: string | null;
    }>;
  };
  return (data.results ?? []).map((p) => ({
    id: p.id,
    name: p.name,
    persona_type: p.persona_type ?? 'established',
    is_fake_name: p.is_fake_name ?? false,
    thumbnail_url: p.thumbnail_url ?? null,
    thumbnail_media_url: p.thumbnail_media_url ?? null,
  }));
}

/** The faces a character can wear (PRIMARY + ESTABLISHED + TEMPORARY masks). */
export function useCharacterPersonasQuery(characterSheetId: number | null) {
  return useQuery({
    queryKey:
      characterSheetId !== null
        ? personaKeys.forCharacterSheet(characterSheetId)
        : ['character-personas', 'none'],
    queryFn: () => fetchCharacterPersonas(characterSheetId as number),
    enabled: characterSheetId !== null,
  });
}

async function setActivePersona(personaId: number): Promise<number> {
  const res = await apiFetch('/api/personas/set-active/', {
    method: 'POST',
    body: JSON.stringify({ persona_id: personaId }),
  });
  if (!res.ok) {
    throw new Error('Could not switch to that identity.');
  }
  const data = (await res.json()) as { active_persona_id: number };
  return data.active_persona_id;
}

/** Switch the worn face. Invalidates the roster bootstrap so the bar re-reads it. */
export function useSetActivePersonaMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (personaId: number) => setActivePersona(personaId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-roster-entries'] });
    },
  });
}
