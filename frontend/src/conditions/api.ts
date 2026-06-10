/**
 * Conditions API client functions.
 *
 * Plain async functions — not hooks. React Query hooks live in queries.ts.
 * Supports the condition-detail modal deep link (#551).
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type ConditionInstance = components['schemas']['ConditionInstance'];

/**
 * Fetch a single condition instance by pk.
 * GET /api/conditions/instances/{id}/
 */
export async function fetchConditionInstance(id: number): Promise<ConditionInstance> {
  const res = await apiFetch(`/api/conditions/instances/${id}/`);
  if (!res.ok) throw new Error('Failed to load condition instance');
  return res.json() as Promise<ConditionInstance>;
}

export type DamageType = components['schemas']['DamageType'];

/**
 * Fetch all damage types (staff-authored lookup data).
 * GET /api/conditions/damage-types/
 */
export async function fetchDamageTypes(): Promise<DamageType[]> {
  const res = await apiFetch('/api/conditions/damage-types/');
  if (!res.ok) throw new Error('Failed to load damage types');
  return res.json() as Promise<DamageType[]>;
}
