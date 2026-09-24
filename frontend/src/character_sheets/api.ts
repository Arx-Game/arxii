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
  /**
   * The distinctive feature this row is aimed at (#3739), by display name; blank for
   * an ordinary distinction. Physical lists the non-blank ones — a feature is
   * something a person can see.
   */
  feature: string;
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
/**
 * Mirrors `world.character_sheets.types.OriginSlotEntry`. `kind`/`connection_kind`/`life_stage`
 * mirror the prompt (#3660); `choice_name`/`choice_description` are the picked choice's own
 * fields. `organization_id`/`organization_name` are the resolved anchor (a GROUP question's
 * pick, or the group a PERSON question's named figure belongs to). `figure_name` is blanked
 * for a non-privileged (foreign) viewer.
 */
export interface CharacterSheetOriginSlot {
  slot_id: number;
  slot_name: string;
  slot_prompt: string;
  value: string;
  kind: string;
  connection_kind: string;
  life_stage: string;
  choice_name: string;
  choice_description: string;
  organization_id: number | null;
  organization_name: string;
  figure_name: string;
}

export interface CharacterSheetStory {
  background: string;
  origin_story_state: string;
  origin_slots: CharacterSheetOriginSlot[];
}

/** Mirrors `world.character_sheets.types.EnemyEntry` (#3621); owner, staff and GM only. */
export interface CharacterSheetEnemy {
  kind: 'person' | 'group';
  name: string;
  power_tier: string;
  reach: string;
  degree: string;
  price: number;
  why: string;
  public_line: string;
  status: string;
  has_secret: boolean;
}

/** Mirrors `world.character_sheets.types.IntroductionEntry` (#3621). */
export interface CharacterSheetIntroduction {
  id: number;
  kind: 'first_journal' | 'application' | 'whispers';
  title: string;
  body: string;
  created_at: string;
}

/** Mirrors `world.character_sheets.types.ActorSheetSection` (#3621). */
export interface CharacterSheetActorSheet {
  never_do: string;
  protect: string;
  fear: string;
  enemy_public_line: string;
  enemy: CharacterSheetEnemy | null;
  introductions: CharacterSheetIntroduction[];
}

/**
 * Mirrors `world.character_sheets.types.PersonaEntry`. A privileged viewer (owner/staff) gets
 * every face of the character; a non-privileged viewer gets exactly one entry — the presented
 * (active) persona — so `personas[0].id` is always a safe "which persona is this sheet
 * currently showing" fallback for a foreign, non-privileged view (#3466).
 */
export interface CharacterSheetPersona {
  id: number;
  name: string;
  thumbnail: string | null;
}

/**
 * Mirrors `world.character_sheets.types.GoalEntry` (#3621) — one numbered goal.
 * The list arrives empty when the viewer's access does not meet `goals_visibility`,
 * which is indistinguishable from "wrote none"; both render as no goals.
 */
export interface CharacterSheetGoal {
  domain: string;
  horizon: string;
  ordinal: number;
  points: number;
  notes: string;
}

/** Mirrors `world.character_sheets.types.IdNameRef`. */
export interface IdNameRef {
  id: number;
  name: string;
}

/** Mirrors `world.character_sheets.types.PronounsData`. */
export interface CharacterSheetPronouns {
  subject: string;
  object: string;
  possessive: string;
}

/** Mirrors `world.character_sheets.types.VacancyRef` (#3648). */
export interface CharacterSheetVacancy {
  name: string;
  presumed_importance: number;
  /** Owner/staff only; null for every other viewer. */
  importance: number | null;
}

/**
 * Mirrors `world.character_sheets.types.IdentitySection`.
 *
 * The age axes, `worship_sincere` and `current_mood` are owner/staff only and arrive
 * null for every other viewer (the leak table) — render them only where the sheet is
 * already showing owner-gated material, and never infer "no mood" from a null.
 */
export interface CharacterSheetIdentity {
  name: string;
  fullname: string;
  concept: string;
  quote: string;
  age: number | null;
  birthday: string | null;
  chronological_age: number | null;
  biological_age: number | null;
  withered_years: number | null;
  gender: IdNameRef | null;
  pronouns: CharacterSheetPronouns;
  species: IdNameRef | null;
  heritage: IdNameRef | null;
  /**
   * Every Beginnings this character holds (#3775) — what the sheet calls their
   * "Beginning". NOT `origin`, which is the realm they are from; binding the
   * Beginning row to `origin` was the bug this replaced.
   */
  beginnings: IdNameRef[];
  family: IdNameRef | null;
  tarot_card: IdNameRef | null;
  origin: IdNameRef | null;
  path: IdNameRef | null;
  worship: IdNameRef | null;
  worship_sincere: boolean | null;
  current_mood: IdNameRef | null;
  vacancy: CharacterSheetVacancy | null;
}

/** Mirrors `world.character_sheets.types.FormTraitEntry` — one hair/eye/skin row. */
export interface CharacterSheetFormTrait {
  trait: string;
  value: string;
}

/**
 * Mirrors `world.character_sheets.types.AppearanceSection`.
 *
 * `height_inches` is owner/staff only (#1325) — everyone else reads `height_band`.
 * `description` is blank unless the presented identity is revealed, so a mask never
 * leaks identifying prose.
 */
export interface CharacterSheetAppearance {
  height_inches: number | null;
  height_band: string | null;
  build: IdNameRef | null;
  description: string;
  form_traits: CharacterSheetFormTrait[];
}

/** Mirrors `world.character_sheets.types.PathHistoryEntry`. */
export interface CharacterSheetPathHistory {
  path: string;
  stage: number;
  tier: string;
  date: string;
}

/** Mirrors `world.character_sheets.types.PathDetailSection`. */
export interface CharacterSheetPath {
  id: number;
  name: string;
  stage: number;
  tier: string;
  history: CharacterSheetPathHistory[];
}

/**
 * Mirrors `world.character_sheets.types.LookEntry` (#3898) — one image of the
 * character, tagged with the mood it shows.
 *
 * `tenure_media_id` is what `POST /api/roster/entries/{pk}/set_profile_picture/`
 * takes, so the owner can wear any look from the sheet. `look` is blank for an
 * untagged image. A non-privileged viewer receives only public-gallery images plus
 * the current one.
 */
export interface CharacterSheetLook {
  tenure_media_id: number;
  url: string;
  title: string;
  look: string;
  is_current: boolean;
}

/** The four plate inks (`world.character_sheets.types.PlateInk`, #3898). */
export type PlateInk = 'ember' | 'verdigris' | 'rose' | 'night';

export interface CharacterSheetPayload {
  id: number;
  can_edit: boolean;
  identity: CharacterSheetIdentity;
  appearance: CharacterSheetAppearance;
  /** Stat name -> display value (already ÷10 from the ×10 internal storage, ADR-0193). */
  stats: Record<string, number>;
  skills: CharacterSheetSkill[];
  path: CharacterSheetPath | null;
  distinctions: CharacterSheetDistinction[];
  magic: CharacterSheetMagic | null;
  story: CharacterSheetStory;
  actor_sheet: CharacterSheetActorSheet;
  goals: CharacterSheetGoal[];
  personas: CharacterSheetPersona[];
  theming: Record<string, unknown>;
  profile_picture: string | null;
  current_residence: IdNameRef | null;
  /** #3898 — the character's images, worn one first. Empty when they have none. */
  looks: CharacterSheetLook[];
  /** #3898 — OOC chrome: the ground colour the plate is printed in. */
  plate_ink: PlateInk;
  /** #3898 — what the character has on, as the layer walk says anyone would see it. */
  worn: CharacterSheetWorn[];
  /** #3898 — active Mentor's Vow bonds. Empty for anyone but the owner and staff. */
  mentors: CharacterSheetMentor[];
  /** #3901 — land the character's organizations hold. Empty for anyone but the owner. */
  domains: CharacterSheetDomain[];
  keyring: CharacterSheetKeyringEntry[];
  /** #3906 — where the presented face stands. Gated by `standing_visibility`. */
  standing: CharacterSheetStanding;
  /** #3906 — active covenant roles. Public. */
  covenants: CharacterSheetCovenantRole[];
  /**
   * #3957 — the cast. One card per active side of a tie, already shaped for the viewer:
   * a third party's cards carry no numbers and a tie with no open Public label is not
   * in this list at all.
   */
  ties: CharacterSheetTie[];
  /**
   * #3957 — AP the owner has set across every tie this week. `null` for anyone but the
   * owner and staff, which is also what says the AP ledger line must not be drawn.
   */
  ties_ap_this_week: number | null;
}

/**
 * Mirrors `world.character_sheets.types.TieLabelEntry` (#3957) — one label on a tie
 * card. `awareness` is `public` for an unmarked label, and a third party only ever
 * receives public, unended ones.
 *
 * `valence` is the label TYPE's warm/hostile/neutral. It rides the card so the cast's
 * chips are colour-coded the way the tie page's already are: without it the grid was
 * monochrome and a reader could not tell a lover from an enemy without opening each
 * tie.
 *
 * `label_id` is the label row's own id and the only safe React key for a chip: two
 * FORMER labels of one type are identical in every other field, so a key built from
 * type/awareness/former collides after declare -> end -> declare -> end.
 */
export interface CharacterSheetTieLabel {
  label_id: number;
  type_name: string;
  awareness: string;
  valence: string;
  is_former: boolean;
  is_mutual: boolean;
}

/**
 * Mirrors `world.character_sheets.types.TieCardEntry` (#3957) — one card on the cast.
 *
 * `depth`/`tier` are null for a third party, and that null IS the instruction: the card
 * prints `summary_line` in place of the numbers rather than a zero. `thread` arrives as
 * the finished sentence the server built, not as its parts.
 */
export interface CharacterSheetTie {
  relationship_id: number;
  other_name: string;
  other_sheet_id: number | null;
  other_entry_id: number | null;
  other_companion_id: number | null;
  labels: CharacterSheetTieLabel[];
  depth: number | null;
  tier: number | null;
  summary_line: string;
  thread: string | null;
}

/**
 * Mirrors `world.character_sheets.types.StandingSection` (#3906) — which houses the
 * presented face belongs to and what each thinks of them. Both lists are empty for a
 * viewer whose access does not meet the character's `standing_visibility`, which
 * defaults to FRIENDS: the only one of the sheet's five tiers that does not default to
 * SELF.
 *
 * Reputation is the NAMED TIER only, never the raw value.
 */
export interface CharacterSheetStanding {
  memberships: { organization_id: number; organization: string; title: string }[];
  reputations: { organization_id: number; organization: string; tier: string }[];
}

/**
 * Mirrors `world.character_sheets.types.CovenantRoleEntry` (#3906) — one active
 * covenant role. Public, the way the Titles block beside it has always been.
 */
export interface CharacterSheetCovenantRole {
  id: number;
  covenant_id: number;
  covenant: string;
  role: string;
  rank: string;
  engaged: boolean;
}

/**
 * Mirrors `world.character_sheets.types.OrgDomainEntry` (#3901) — one landholding an
 * organization this character belongs to owns. A domain is never the character's own;
 * the row says whose it is and where, so a player new to the character can find it.
 */
export interface CharacterSheetDomain {
  id: number;
  name: string;
  organization: string;
  where: string;
}

/**
 * Mirrors `world.character_sheets.types.KeyringEntry` (#3902) — one place this
 * character may walk into, and on whose authority.
 *
 * The discovery half of the guest-key ruling: a friend hands this character a key and
 * nothing on the sheet could say the house exists, so the next player of that
 * character never learns it. A family keep reached through an organization is the
 * same row with `through` filled in.
 *
 * `rung` is the human label of the grant's role (Guest / Tenant / Trustee), never a
 * raw value. `through` and `granted_by` are empty strings rather than null when they
 * do not apply — an org-less grant and a world-granted one respectively.
 */
export interface CharacterSheetKeyringEntry {
  id: number;
  place: string;
  where: string;
  rung: string;
  through: string;
  granted_by: string;
}

/**
 * Mirrors `world.character_sheets.types.MentorBondEntry` (#3898) — one active Mentor's
 * Vow bond. `role` says what the OTHER party is to this character: their Mentor, or
 * their Student.
 */
export interface CharacterSheetMentor {
  id: number;
  name: string;
  role: string;
  covenant: string;
}

/**
 * Mirrors `world.character_sheets.types.WornEntry` (#3898) — one piece the character
 * is wearing. `is_hidden` is only ever true for the owner and staff: a piece the layer
 * walk says is covered is dropped for everyone else.
 */
export interface CharacterSheetWorn {
  id: number;
  name: string;
  description: string;
  is_hidden: boolean;
}

export async function fetchCharacterSheet(sheetId: number): Promise<CharacterSheetPayload> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/`);
  if (!res.ok) throw new Error('Failed to load character sheet');
  return (await res.json()) as CharacterSheetPayload;
}
