import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';

export type PersonaType = 'primary' | 'established' | 'temporary' | 'alternate';

/** A face a character can present as, for the top-bar switcher. */
export interface SwitchablePersona {
  id: number;
  name: string;
  persona_type: PersonaType;
  is_fake_name: boolean;
  thumbnail_url: string | null;
  thumbnail_media_url: string | null;
  /** #1682 — the guise's fabricated bio (empty strings when unauthored). */
  guise_concept: string;
  guise_quote: string;
  guise_personality: string;
  guise_background: string;
}

/** #1682 — the four authorable Guise-Sheet fields. */
export interface GuiseProfileBody {
  concept: string;
  quote: string;
  personality: string;
  background: string;
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
      guise_concept?: string;
      guise_quote?: string;
      guise_personality?: string;
      guise_background?: string;
    }>;
  };
  return (data.results ?? []).map((p) => ({
    id: p.id,
    name: p.name,
    persona_type: p.persona_type ?? 'established',
    is_fake_name: p.is_fake_name ?? false,
    thumbnail_url: p.thumbnail_url ?? null,
    thumbnail_media_url: p.thumbnail_media_url ?? null,
    guise_concept: p.guise_concept ?? '',
    guise_quote: p.guise_quote ?? '',
    guise_personality: p.guise_personality ?? '',
    guise_background: p.guise_background ?? '',
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
    // #3412 slice 3 task 5 — was a fixed generic message; now surfaces the
    // response's `{"detail"}` (e.g. an offscreen-gate refusal reason) when
    // present, falling back to the same generic copy otherwise. Mirrors the
    // journals/goals composers' `readErrorDetail` convention (`lib/errors.ts`)
    // rather than `postSelectEntry`'s fixed-message pattern this fetcher
    // previously copied — see task-4-report's "known limitation" note.
    await readErrorDetail(res, 'Could not switch to that identity.');
  }
  const data = (await res.json()) as { active_persona_id: number };
  return data.active_persona_id;
}

/**
 * Switch the worn face. Invalidates the roster bootstrap so the bar re-reads it.
 *
 * `onError` (#3412 T4 folded-in review finding) — previously errors here (including
 * an offscreen-gate refusal on a CAPTURED/unconscious/DEAD/RETIRED character, #3412
 * slice 3) rendered NOWHERE: both `PersonaSwitcher` and `PersonaTiles` call `.mutate()`
 * without a per-call `onError`, so a failed switch silently did nothing. Mirrors
 * `useSelectCharacterMutation`'s exact onError/toast pattern
 * (`frontend/src/roster/queries.ts`) — PLACEHOLDER copy.
 */
export function useSetActivePersonaMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (personaId: number) => setActivePersona(personaId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-roster-entries'] });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : 'Could not switch to that identity.'),
  });
}

async function setPersonaProfile(personaId: number, body: GuiseProfileBody): Promise<void> {
  const res = await apiFetch('/api/personas/set-profile/', {
    method: 'POST',
    body: JSON.stringify({ persona_id: personaId, ...body }),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as string[] | null;
    throw new Error(Array.isArray(detail) ? detail[0] : 'Could not save the guise sheet.');
  }
}

/** #1682 — author a cover persona's Guise Sheet; refreshes the persona list on save. */
export function useSetPersonaProfileMutation(characterSheetId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ personaId, body }: { personaId: number; body: GuiseProfileBody }) =>
      setPersonaProfile(personaId, body),
    onSuccess: () => {
      if (characterSheetId !== null) {
        qc.invalidateQueries({ queryKey: personaKeys.forCharacterSheet(characterSheetId) });
      }
    },
  });
}
