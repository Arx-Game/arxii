/**
 * Types for the Sanctum subsystem of the magic module (Plan 4 §F).
 *
 * SanctumDetails comes from the generated schema; the action request
 * bodies are declared locally because the viewset's `@action` endpoints
 * don't carry `@extend_schema(request=...)` annotations — drf-spectacular
 * emits `requestBody?: never` for them. Matches the same local-types
 * pattern documented in `frontend/src/magic/CLAUDE.md` for SoulTether.
 */

import type { components } from '@/generated/api';

export type SanctumDetails = components['schemas']['SanctumDetails'];

export interface HomecomingRequest {
  resonance_sacrificed: number;
  narrative_text?: string;
}

export interface HomecomingResult {
  base_resonance_added: number;
  overflow_escrowed: number;
  new_homecoming_sum: number;
  new_cap: number;
}

export interface PurgingRequest {
  new_resonance_id: number;
  resonance_sacrificed: number;
}

export interface PurgingResult {
  new_resonance_id: number;
  sum_after_drain: number;
  sacrifice_paid: number;
}

export type SanctumSlotKind = 'PERSONAL_OWN' | 'COVENANT' | 'HELPER';

export interface WeaveRequest {
  slot_kind: SanctumSlotKind;
}

export interface SanctumThread {
  id: number;
  owner: number;
  target_sanctum_details: number;
  slot_kind: SanctumSlotKind;
  level: number;
  developed_points: number;
  created_at: string;
  retired_at: string | null;
}
