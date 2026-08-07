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
import type { TechniqueEffectSummary, TechniqueForm, TechniqueSignature } from '@/magic/types';

/** Mirrors `world.character_sheets.types.TechniqueEntry`. */
export interface CharacterSheetTechnique {
  name: string;
  level: number;
  style: string;
  description: string;
  /** The shared effect block (#2898) — cost, reach, targeting, hostility, plain-words summary. */
  effect_summary: TechniqueEffectSummary;
  /**
   * Which forms of it this caster can work (#2901): base, each unlocked
   * variant, and one step ahead. Always at least one entry. The sheet
   * describes, so it carries the full catalogue; the cast list carries only a
   * compact affordance.
   */
  forms: TechniqueForm[];
  /** The signature flourish riding whichever form is chosen, if any. */
  signature: TechniqueSignature | null;
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

/** Mirrors `world.character_sheets.types.ResonanceBalanceEntry`. */
export interface CharacterSheetResonanceBalance {
  name: string;
  balance: number;
  lifetime_earned: number;
}

/** Mirrors `world.character_sheets.types.MagicSection`. */
export interface CharacterSheetMagic {
  gifts: CharacterSheetGift[];
  motif: CharacterSheetMotif | null;
  anima_ritual: CharacterSheetAnimaRitual | null;
  aura: CharacterSheetAura | null;
  /** Claimed-resonance spendable balances (#2032/#3042) — sorted by name server-side. */
  resonances: CharacterSheetResonanceBalance[];
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

/** Mirrors `world.character_sheets.types.SkillRef`. */
export interface CharacterSheetSkillRef {
  id: number;
  name: string;
  category: string;
}

/** Mirrors `world.character_sheets.types.SpecializationEntry`. */
export interface CharacterSheetSpecialization {
  id: number;
  name: string;
  value: number;
}

/** Mirrors `world.character_sheets.types.SkillEntry`. */
export interface CharacterSheetSkill {
  skill: CharacterSheetSkillRef;
  value: number;
  /** True when the skill is parked at an XP boundary (19/29/39/49) — a breakthrough check. */
  at_boundary: boolean;
  specializations: CharacterSheetSpecialization[];
}

/**
 * The full `/api/character-sheets/{id}/` payload.
 *
 * `identity`, `appearance`, `path`, `story`, `goals`, `personas`, `theming`, `profile_picture`,
 * and `current_residence` are left loosely typed here — refine as their consuming sections land.
 * `stats` and `skills` were typed precisely in #3042 (mirroring
 * `world.character_sheets.types._build_stats`/`SkillEntry`); `distinctions` and `magic` in
 * Tasks 9 & 10.
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
  /** Stat name -> display value (already ÷10 from the ×10 internal storage, ADR-0193). */
  stats: Record<string, number>;
  skills: CharacterSheetSkill[];
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
