/**
 * Conditions React Query hooks.
 *
 * Backs the condition-detail modal deep link (#551).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchConditionInstance, fetchDamageTypes, fetchTreatmentCandidates } from './api';

/**
 * Fetch a single condition instance by pk.
 * Disabled when id is null (modal closed).
 */
export function useConditionInstance(id: number | null) {
  return useQuery({
    queryKey: ['conditionInstance', id],
    queryFn: () => fetchConditionInstance(id as number),
    enabled: id != null,
    staleTime: 30_000,
  });
}

/** Damage types are staff-authored lookup data — cache aggressively. */
export function useDamageTypes() {
  return useQuery({
    queryKey: ['conditions', 'damage-types'],
    queryFn: fetchDamageTypes,
    staleTime: 5 * 60_000,
  });
}

/**
 * Fetch treatments the helper may offer a target persona (#1486).
 * Disabled when either id is null: targetPersonaId (no target chosen) or
 * characterId (no active character resolved for the X-Character-ID header).
 */
export function useTreatmentCandidates(targetPersonaId: number | null, characterId: number | null) {
  return useQuery({
    queryKey: ['conditions', 'treatment-candidates', targetPersonaId],
    queryFn: () => fetchTreatmentCandidates(targetPersonaId as number, characterId as number),
    enabled: targetPersonaId != null && characterId != null,
  });
}
