/**
 * Types for the GM adjudication toolkit's web panel (#3070).
 *
 * The panel dispatches five existing REGISTRY actions
 * (`gm_invoke_check`, `gm_award_progression`, `gm_apply_condition`,
 * `set_situation`, `place_challenge` — `src/actions/definitions/gm_adjudication.py`
 * / `situations.py`) via the generic REST dispatch seam
 * (`useDispatchPlayerAction` -> `POST /api/actions/characters/{id}/dispatch/`).
 * None of these actions carry an `ActionTemplate`, so they never appear in
 * `get_player_actions` — the panel builds its own `ActionRef`s directly,
 * mirroring `PersonaContextMenu.tsx`'s `challenge`/`identify` dispatches.
 */

import type { components } from '@/generated/api';

/** GM catalog browse row for the Call Check picker (GET /api/checks/check-types/). */
export type CheckTypeCatalogEntry = components['schemas']['CheckType'];

/** Condition catalog row (GET /api/conditions/templates/ — bare array, no pagination). */
export type ConditionTemplateCatalogEntry = components['schemas']['ConditionTemplate'];

/** Situation catalog row (GET /api/mechanics/situation-templates/). */
export type SituationTemplateCatalogEntry = components['schemas']['SituationTemplateList'];

/** Challenge catalog row (GET /api/mechanics/challenge-templates/). */
export type ChallengeTemplateCatalogEntry = components['schemas']['ChallengeTemplateList'];

/**
 * Item template catalog row for the Grant Item / Stage Prop pickers (#3431),
 * GET /api/items/templates/ (`ItemTemplateViewSet`, `name` icontains filter) —
 * the existing catalog endpoint, no new one added (Decision 3).
 */
export type ItemTemplateCatalogEntry = components['schemas']['ItemTemplateList'];

/**
 * One row of `gm_list_conditions`'s result data (#3431) — a target's active
 * `ConditionInstance`s, feeding the Condition tab's Remove-mode picker. Not a
 * generated schema type: this is `ActionResult.data` from a REGISTRY dispatch,
 * not a ViewSet response (see `GMListConditionsAction`,
 * `actions/definitions/gm_adjudication.py`).
 */
export interface ActiveConditionEntry {
  id: number;
  name: string;
  severity: number;
  rounds_remaining: number | null;
  expires_at: string | null;
}

/** One row of `list_room_traps`'s result data (#3002/#3431). Same non-ViewSet
 *  shape as `ActiveConditionEntry` — see `ListRoomTrapsAction`,
 *  `actions/definitions/traps.py`. */
export interface RoomTrapEntry {
  id: number;
  name: string;
  is_armed: boolean;
  position: string | null;
}

/**
 * One row of `gm_list_runnable_beats`'s result data (#3425) — an
 * ENCOUNTER/SITUATION beat, or a TASK beat carrying a scenario
 * (`has_scenario`, #3565), on the acting GM's currently-active episode, ready
 * to run into the scene. `staged_battle_name` (#3569) names the blueprint an
 * ENCOUNTER beat will stage a battle from, or null when it stages none. Same
 * non-ViewSet shape as `RoomTrapEntry`; see `GMListRunnableBeatsAction`,
 * `actions/definitions/gm_story.py`.
 */
export interface RunnableBeatEntry {
  id: number;
  story_title: string;
  episode_title: string;
  kind: 'encounter' | 'situation' | 'task';
  risk: string;
  opponent_line_count: number;
  staged_template_count: number;
  has_scenario: boolean;
  staged_battle_name: string | null;
}

/** Mirrors `world.scenes.action_constants.DifficultyChoice` — the only bands
 *  `gm_invoke_check` accepts (never a free integer). */
export const DIFFICULTY_BANDS = [
  { value: 'trivial', label: 'Trivial' },
  { value: 'easy', label: 'Easy' },
  { value: 'normal', label: 'Normal' },
  { value: 'hard', label: 'Hard' },
  { value: 'daunting', label: 'Daunting' },
  { value: 'harrowing', label: 'Harrowing' },
] as const;

export type DifficultyBand = (typeof DIFFICULTY_BANDS)[number]['value'];

/** Mirrors `GMAwardAction`'s `award_type` dispatch (`_AWARD_TYPES`). */
export const AWARD_KINDS = [
  { value: 'xp', label: 'XP' },
  { value: 'development', label: 'Development Points' },
  { value: 'favor_token', label: 'Golden Hare (Favor Token)' },
  { value: 'stat', label: 'Stat Raise' },
  { value: 'technique', label: 'Technique Grant' },
] as const;

export type AwardKind = (typeof AWARD_KINDS)[number]['value'];

/**
 * A pending GM summon offer (#3071), GET /api/gm/summon-offers/.
 *
 * Leak analysis (spec-approved): only `gm_display_name` + `scene_title` are
 * exposed — never room contents or other occupants.
 */
export type GMSummonOfferEntry = components['schemas']['GMSummonOffer'];
