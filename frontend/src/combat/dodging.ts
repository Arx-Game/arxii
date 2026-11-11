/**
 * Shared helpers for dodging and area attacks (#4676): the dodge-plan request, the
 * attacks covering a place, and the telegraph's line.
 */

import type { PullSelection } from '@/magic/components/threads/ThreadPullDialog';
import type { DispatchActionRequest, PendingAttack } from './types';

export const DODGE_REGISTRY_KEY = 'combat_dodge';

/** A `combat_dodge` registry dispatch with these kwargs. */
export function dodgeRequest(kwargs: Record<string, unknown>): DispatchActionRequest {
  return { ref: { backend: 'registry', registry_key: DODGE_REGISTRY_KEY }, kwargs };
}

export const DODGE_SETTINGS_REGISTRY_KEY = 'dodge_settings';

/**
 * A `dodge_settings` dispatch (#5066): the technique answering her dodges (`technique_id`,
 * "" for her default; `save_default` keeps it for every fight), `into_soulfray`, and the
 * defensive pull (`auto_pull`, with `pull_resonance_id` and `pull_tier` when turning it on).
 */
export function dodgeSettingsRequest(kwargs: Record<string, unknown>): DispatchActionRequest {
  return { ref: { backend: 'registry', registry_key: DODGE_SETTINGS_REGISTRY_KEY }, kwargs };
}

export const ROUND_PULL_REGISTRY_KEY = 'combat_pull';

/** A `combat_pull` dispatch: a thread pull declared on its own for the round (#5066). */
export function roundPullRequest(selection: PullSelection): DispatchActionRequest {
  return {
    ref: { backend: 'registry', registry_key: ROUND_PULL_REGISTRY_KEY },
    kwargs: {
      pull_tier: selection.tier,
      pull_thread_ids: selection.thread_ids,
    },
  };
}

export const STEADY_REGISTRY_KEY = 'combat_steady';

/** A `combat_steady` registry dispatch turning the steady plan on or off. */
export function steadyRequest(steady: boolean): DispatchActionRequest {
  return { ref: { backend: 'registry', registry_key: STEADY_REGISTRY_KEY }, kwargs: { steady } };
}

/** The pending attacks that will cover the place with this id. */
export function attacksCoveringPlace(
  attacks: PendingAttack[],
  positionId: number | null
): PendingAttack[] {
  if (positionId === null) return [];
  return attacks.filter((a) => !a.cancelled && a.covered_position_id === positionId);
}

/** "Holy fire lands here at the end of this round." and its later variants. */
export function telegraphLine(attackName: string, roundsUntilLanding: number): string {
  if (roundsUntilLanding <= 0) return `${attackName} lands here at the end of this round`;
  if (roundsUntilLanding === 1) return `${attackName} lands here next round`;
  return `${attackName} lands here in ${roundsUntilLanding} rounds`;
}
