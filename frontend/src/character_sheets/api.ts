/**
 * Character sheet API client (#1446) — the rich per-character payload.
 *
 * Reads `/api/character-sheets/{id}/` (sheet id == character id). The view's
 * `CharacterSheetSerializer` (src/world/character_sheets/serializers.py) overrides
 * `to_representation` directly instead of declaring fields, so drf-spectacular can't infer a
 * response schema for it — `schema.json` / `generated/api.d.ts` record this operation as
 * "No response body" (no `components['schemas']['CharacterSheet']` exists). `CharacterSheetPayload`
 * is therefore hand-written to mirror the serializer's `to_representation` dict and the section
 * TypedDicts in `src/world/character_sheets/types.py`, not sourced from the generated schema.
 */

import { apiFetch } from '@/evennia_replacements/api';

/** Mirrors `world.character_sheets.types.TechniqueEntry`. */
export interface CharacterSheetTechnique {
  name: string;
  level: number;
  style: string;
  description: string;
}

/** Mirrors `world.character_sheets.types.GiftEntry`. */
export interface CharacterSheetGift {
  name: string;
  description: string;
  resonances: string[];
  techniques: CharacterSheetTechnique[];
}

/** Mirrors `world.character_sheets.types.MotifResonanceEntry`. */
export interface CharacterSheetMotifResonance {
  name: string;
  facets: string[];
  /** Styles bound to this resonance (#2030) — `Style.name` for each MotifStyleBinding. */
  styles: string[];
}

/** Mirrors `world.character_sheets.types.MotifSection`. */
export interface CharacterSheetMotif {
  description: string;
  resonances: CharacterSheetMotifResonance[];
}

/** Mirrors `world.character_sheets.types.AnimaRitualSection`. */
export interface CharacterSheetAnimaRitual {
  stat: string;
  skill: string;
  resonance: string;
  description: string;
}

/** Mirrors `world.character_sheets.types.GlimpseTagEntry`. */
export interface CharacterSheetGlimpseTag {
  id: number;
  axis: string;
  name: string;
  description: string;
}

/** Mirrors `world.character_sheets.types.AuraData`. */
export interface CharacterSheetAura {
  /** CharacterAura pk — the id the aura action endpoints (`/api/magic/character-auras/{id}/...`) key on. */
  id: number;
  celestial: number;
  primal: number;
  abyssal: number;
  glimpse_story: string;
  glimpse_state: 'NOT_STARTED' | 'TAGS_ONLY' | 'COMPLETE';
  glimpse_tags: CharacterSheetGlimpseTag[];
  /** Owner-only affordance: true unless the viewer isn't privileged or the glimpse is already COMPLETE. */
  can_finish_glimpse: boolean;
}

/** Mirrors `world.character_sheets.types.MagicSection`. */
export interface CharacterSheetMagic {
  gifts: CharacterSheetGift[];
  motif: CharacterSheetMotif | null;
  anima_ritual: CharacterSheetAnimaRitual | null;
  aura: CharacterSheetAura | null;
}

/** Mirrors `world.character_sheets.types.DistinctionEntry`. */
export interface CharacterSheetDistinction {
  /** CharacterDistinction pk — matches the aura glimpse-link endpoints' `character_distinction_id`. */
  id: number;
  name: string;
  rank: number;
  notes: string;
  is_secret: boolean;
  /** True when `CharacterDistinction.from_glimpse` points at this character's aura (#2427). */
  is_from_glimpse: boolean;
}

/**
 * The full `/api/character-sheets/{id}/` payload.
 *
 * `identity`, `appearance`, `stats`, `skills`, `path`, `story`, `goals`, `personas`, `theming`,
 * `profile_picture`, and `current_residence` are left loosely typed here — this task only needs
 * `distinctions` and `magic` typed precisely (Tasks 9 & 10); refine the rest as their consuming
 * sections land.
 */
export interface CharacterSheetOriginSlot {
  slot_id: number;
  slot_name: string;
  slot_prompt: string;
  value: string;
}

export interface CharacterSheetStory {
  background: string;
  personality: string;
  origin_story_state: string;
  origin_slots: CharacterSheetOriginSlot[];
}

export interface CharacterSheetPayload {
  id: number;
  can_edit: boolean;
  identity: Record<string, unknown>;
  appearance: Record<string, unknown>;
  stats: Record<string, unknown>;
  skills: unknown[];
  path: Record<string, unknown> | null;
  distinctions: CharacterSheetDistinction[];
  magic: CharacterSheetMagic | null;
  story: CharacterSheetStory;
  goals: unknown[];
  personas: unknown[];
  theming: Record<string, unknown>;
  profile_picture: unknown;
  current_residence: unknown;
}

export async function fetchCharacterSheet(sheetId: number): Promise<CharacterSheetPayload> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/`);
  if (!res.ok) throw new Error('Failed to load character sheet');
  return (await res.json()) as CharacterSheetPayload;
}
