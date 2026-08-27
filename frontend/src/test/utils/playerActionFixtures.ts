/**
 * Shared PlayerAction test-fixture builders (#3385).
 *
 * Most tests build their own small, local PlayerAction fixture inline (an
 * established per-file convention across this codebase's test suites, since
 * most fixtures need file-specific shapes). This module exists specifically
 * for `gm_place_in_position` — its fixture was duplicated byte-for-byte
 * across `CombatTacticalMap.test.tsx` and `SceneTacticalMap.test.tsx`, both
 * exercising the same #3385 GM-place picker, so it earns a shared home
 * rather than a third copy the next time a GM-place test is added.
 */

import type { PlayerAction } from '@/scenes/actionTypes';

/** A `gm_place_in_position` registry PlayerAction targeting `positionId`. */
export function makeGMPlaceAction(positionId: number): PlayerAction {
  return {
    backend: 'registry',
    display_name: `Place in position: ${positionId}`,
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'registry',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: 'gm_place_in_position',
      position_id: positionId,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}
