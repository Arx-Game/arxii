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
  | 'relationship_capstone_picker'
  | 'covenant_picker'
  | 'covenant_role_picker'
  | 'soul_tether_role_picker';

export interface RitualField {
  name: string;
  label: string;
  type: string;
  required?: boolean;
  help?: string;
  scope?: string;
  choices?: Array<{ value: string | number; label: string }>;
  /**
   * Name of another form field this field depends on for filtering.
   * May be a sibling field name (e.g. "covenant_type") or a session-level
   * reference path (e.g. "session.target_covenant.covenant_type") — the
   * latter is resolved by the parent form or dialog.
   */
  depends_on?: string;
  /** Hint for server-side filtering when fetching options (e.g. "initiator_active_memberships"). */
  filter?: string;
}

export interface FieldProps {
  field: RitualField;
  value: string | number | null;
  onChange: (value: string | number | null) => void;
  disabled?: boolean;
  /**
   * Other form field values — used by fields with cross-field dependencies.
   * For example, RelationshipCapstonePickerField reads `formValues.sineater_sheet_id`
   * to filter capstones by the selected sineater's character sheet.
   */
  formValues?: Record<string, string | number | null>;
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
