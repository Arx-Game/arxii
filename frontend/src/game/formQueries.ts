import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/evennia_replacements/api';

/** An alternate self the player can shift into (#1111). */
export interface SwitchableAlternateSelf {
  id: number;
  display_name: string;
  persona_name: string | null;
  form_name: string | null;
  has_combat_profile: boolean;
  has_techniques: boolean;
  is_active: boolean;
}

const alternateSelfKeys = {
  forCharacterSheet: (characterSheetId: number) =>
    ['character-alternate-selves', characterSheetId] as const,
};

async function fetchAlternateSelves(characterSheetId: number): Promise<SwitchableAlternateSelf[]> {
  const res = await apiFetch(
    `/api/forms/alternate-selves/?character_sheet=${characterSheetId}&page_size=100`
  );
  if (!res.ok) {
    throw new Error('Failed to load alternate selves.');
  }
  const data = (await res.json()) as {
    results?: Array<{
      id: number;
      display_name?: string;
      persona_name?: string | null;
      form_name?: string | null;
      has_combat_profile?: boolean;
      has_techniques?: boolean;
      is_active?: boolean;
    }>;
  };
  return (data.results ?? []).map((alt) => ({
    id: alt.id,
    display_name: alt.display_name ?? '',
    persona_name: alt.persona_name ?? null,
    form_name: alt.form_name ?? null,
    has_combat_profile: alt.has_combat_profile ?? false,
    has_techniques: alt.has_techniques ?? false,
    is_active: alt.is_active ?? false,
  }));
}

/** The alternate selves available to a character. */
export function useAlternateSelvesQuery(characterSheetId: number | null) {
  return useQuery({
    queryKey:
      characterSheetId !== null
        ? alternateSelfKeys.forCharacterSheet(characterSheetId)
        : ['character-alternate-selves', 'none'],
    queryFn: () => fetchAlternateSelves(characterSheetId as number),
    enabled: characterSheetId !== null,
  });
}

async function shiftForm(alternateSelfId: number): Promise<number | null> {
  const res = await apiFetch('/api/forms/alternate-selves/shift/', {
    method: 'POST',
    body: JSON.stringify({ alternate_self_id: alternateSelfId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body.detail as string | string[])
        : undefined;
    const message = Array.isArray(detail) ? detail.join(' ') : detail;
    throw new Error(message ?? 'Could not assume that alternate self.');
  }
  const data = (await res.json()) as { active_alternate_self_id: number | null };
  return data.active_alternate_self_id;
}

/** Assume an alternate self. Invalidates roster + alternate-self caches. */
export function useShiftFormMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alternateSelfId: number) => shiftForm(alternateSelfId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-roster-entries'] });
      qc.invalidateQueries({ queryKey: ['character-alternate-selves'] });
    },
  });
}

async function revertForm(): Promise<number | null> {
  const res = await apiFetch('/api/forms/alternate-selves/revert/', {
    method: 'POST',
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body.detail as string | string[])
        : undefined;
    const message = Array.isArray(detail) ? detail.join(' ') : detail;
    throw new Error(message ?? 'Could not revert forms.');
  }
  const data = (await res.json()) as { active_alternate_self_id: number | null };
  return data.active_alternate_self_id;
}

/** Revert the active alternate self. Invalidates roster + alternate-self caches. */
export function useRevertFormMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => revertForm(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-roster-entries'] });
      qc.invalidateQueries({ queryKey: ['character-alternate-selves'] });
    },
  });
}
