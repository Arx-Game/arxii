import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { RenownEligiblePersona, RenownPayload } from './types';

async function fetchPersonasForSheet(characterSheetId: number): Promise<RenownEligiblePersona[]> {
  // Fetch every persona on this sheet, then filter client-side to the
  // two types that have renown panels. PersonaFilter supports
  // ``character_sheet`` but not multi-type IN; the result set per body
  // is small enough that one extra round-trip would cost more than the
  // client-side filter.
  const res = await apiFetch(`/api/personas/?character_sheet=${characterSheetId}&page_size=50`);
  if (!res.ok) {
    throw new Error('Failed to load personas for renown tab.');
  }
  const data = (await res.json()) as {
    results?: Array<{ id: number; name: string; persona_type: string }>;
  };
  return (data.results ?? [])
    .filter((p) => p.persona_type === 'primary' || p.persona_type === 'established')
    .map((p) => ({
      id: p.id,
      name: p.name,
      persona_type: p.persona_type as 'primary' | 'established',
    }));
}

async function fetchPersonaRenown(personaId: number): Promise<RenownPayload> {
  const res = await apiFetch(`/api/personas/${personaId}/renown/`);
  if (!res.ok) {
    throw new Error('Failed to load renown.');
  }
  return res.json();
}

export function useRenownEligiblePersonasQuery(characterSheetId: number | null) {
  return useQuery({
    queryKey: ['renown-personas', characterSheetId],
    queryFn: () => fetchPersonasForSheet(characterSheetId as number),
    enabled: characterSheetId !== null,
  });
}

export function usePersonaRenownQuery(personaId: number | null) {
  return useQuery({
    queryKey: ['renown', personaId],
    queryFn: () => fetchPersonaRenown(personaId as number),
    enabled: personaId !== null,
  });
}
