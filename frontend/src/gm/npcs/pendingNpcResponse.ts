import type { Interaction } from '@/scenes/types';

/**
 * The action that is waiting on the NPC being played (#4418): the latest resolved-action
 * row (mode `action`, the machine-written record `_create_result_interaction` makes) that
 * names the NPC's persona as a target, unless that persona has posted since. The player's
 * pose that carries the action as an attachment names no target, so it never matches.
 */
export function pendingNpcResponse(
  interactions: Interaction[],
  npcPersonaId: number
): Interaction | null {
  for (let i = interactions.length - 1; i >= 0; i--) {
    const row = interactions[i];
    if (row.persona.id === npcPersonaId) return null;
    if (row.mode === 'action' && row.target_persona_ids.includes(npcPersonaId)) return row;
  }
  return null;
}

/** The player's pose that attached this action, when one has been posted. */
export function poseCarryingAction(interactions: Interaction[], action: Interaction) {
  return (
    interactions.find((row) =>
      (row.action_links ?? []).some((link) => link.action_interaction.id === action.id)
    ) ?? null
  );
}
