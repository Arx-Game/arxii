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

/**
 * Discriminator for a treatment candidate's target effect type — mirrors the
 * backend TARGET_EFFECT_CONDITION / TARGET_EFFECT_ALTERATION plain strings
 * (src/world/conditions/constants.py). Determines which id field to send on the
 * action-request body: condition → target_condition_instance_id,
 * alteration → target_pending_alteration_id.
 */
export type TargetEffectType = 'condition' | 'alteration';

/**
 * A treatment template row surfaced by the treatments discovery endpoint.
 * Mirrors TreatmentTemplateSerializer (src/world/conditions/serializers.py).
 */
export interface TreatmentTemplate {
  id: number;
  key: string;
  name: string;
  description: string;
  target_kind: string;
  requires_bond: boolean;
  resonance_cost: number;
  anima_cost: number;
  scene_required: boolean;
  target_condition: number | null;
}

/**
 * A treatable target effect.  ConditionInstanceSerializer exposes a `name`
 * (the condition name); PendingAlterationSerializer exposes `character_name` +
 * `status`.  Both carry `id`, which is the value sent on the request body.
 */
export interface TreatmentTargetEffect {
  id: number;
  /** ConditionInstance.name (condition name).  Absent for alterations. */
  name?: string;
  /** PendingAlteration.character_name.  Absent for conditions. */
  character_name?: string;
  [key: string]: unknown;
}

/**
 * One candidate (treatment, target_effect) pair the helper may offer the target.
 *
 * The discovery endpoint serializes `bond_thread` as the thread's id (a number
 * or null), NOT an object — so `bond_thread` is sent directly as
 * `bond_thread_id` on the action-request body.
 *
 * The generated schema marks this endpoint's response as `content?: never`
 * (drf-spectacular emits no component for the ViewSet's hand-built Response),
 * so this interface is the canonical client-side shape.  Source of truth:
 * TreatmentCandidateViewSet.list (src/world/conditions/views.py).
 */
export interface TreatmentCandidate {
  treatment: TreatmentTemplate;
  target_effect_type: TargetEffectType;
  target_effect: TreatmentTargetEffect;
  /** The helper's bond thread id anchored to the target, or null. */
  bond_thread: number | null;
  scene_id: number;
}

/** Response body for GET /api/conditions/treatments/?target_persona_id=<id>. */
export interface TreatmentCandidatesResponse {
  candidates: TreatmentCandidate[];
  scene_id: number;
}

/**
 * Fetch treatments the helper may offer a target persona.
 * GET /api/conditions/treatments/?target_persona_id=<id>
 *
 * The backend resolves the helper via the `X-Character-ID` header (the
 * character ObjectDB pk, not the persona id) — the same header pattern used by
 * the progression path-intent endpoints.
 */
export async function fetchTreatmentCandidates(
  targetPersonaId: number,
  characterId: number
): Promise<TreatmentCandidatesResponse> {
  const res = await apiFetch(`/api/conditions/treatments/?target_persona_id=${targetPersonaId}`, {
    headers: { 'X-Character-ID': String(characterId) },
  });
  if (!res.ok) throw new Error('Failed to load treatment candidates');
  return res.json() as Promise<TreatmentCandidatesResponse>;
}
