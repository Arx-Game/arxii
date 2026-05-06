/**
 * Types for the rituals module.
 *
 * The generated `Ritual.input_schema` is typed as `unknown` because the
 * OpenAPI schema uses a freeform blob. `RitualWithSchema` provides a typed
 * overlay so callers never cast to `any`.
 */

import type { components } from '@/generated/api';

export type Ritual = components['schemas']['Ritual'];
export type PaginatedRitualList = components['schemas']['PaginatedRitualList'];

export type RitualFieldType =
  | 'text'
  | 'int'
  | 'select'
  | 'character_search'
  | 'scene_picker'
  | 'resonance_picker'
  | 'relationship_capstone_picker';

export interface RitualField {
  name: string;
  label: string;
  type: string;
  required?: boolean;
  help?: string;
  scope?: string;
  choices?: Array<{ value: string | number; label: string }>;
}

export interface RitualInputSchema {
  fields: RitualField[];
}

/** Ritual with a typed `input_schema` overlay (generated type uses `unknown`). */
export interface RitualWithSchema extends Omit<Ritual, 'input_schema'> {
  input_schema: RitualInputSchema | null;
}

export interface PerformRitualRequest {
  ritual_id: number;
  character_sheet_id: number;
  kwargs: Record<string, string | number | boolean | null>;
  components?: number[];
}

export interface PerformRitualResponse {
  ritual_id: number;
  execution_kind: string;
  result?: Record<string, unknown>;
}
