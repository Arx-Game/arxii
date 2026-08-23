/**
 * Types for scene check invocation (#3295): the player self-check picker and
 * the GM call-for-check prompt inbox.
 *
 * `DIFFICULTY_BANDS`/`DifficultyBand` are NOT redefined here — reused from
 * `@/gm-adjudication/types`, the single source of truth mirroring
 * `world.scenes.action_constants.DifficultyChoice` (the only bands any check
 * invocation surface accepts — never a free integer).
 */

import type { components } from '@/generated/api';

export { DIFFICULTY_BANDS } from '@/gm-adjudication/types';
export type { DifficultyBand } from '@/gm-adjudication/types';

/** Player-facing catalog browse row (GET /api/checks/player-check-types/). */
export type PlayerCheckTypeEntry = components['schemas']['CheckType'];

/**
 * One of the requesting player's pending `CheckCall` prompts
 * (GET /api/checks/check-call-targets/ — bare array, `pagination_class = None`).
 *
 * Hand-authored (not `components['schemas']`) — `CheckCallTargetSerializer` is a
 * plain `serializers.Serializer`, not exposed through drf-spectacular's model
 * introspection the way `components['schemas']['CheckType']` is.
 */
export interface CheckCallTargetEntry {
  id: number;
  call_id: number;
  check_type_name: string;
  band: string;
  band_label: string;
  caller_display_name: string;
  scene_id: number | null;
  created_at: string;
}
