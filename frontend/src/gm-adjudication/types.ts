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
