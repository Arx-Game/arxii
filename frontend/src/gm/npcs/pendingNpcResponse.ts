import type { Interaction } from '@/scenes/types';

/**
 * The action that is waiting on the NPC being played (#4418): the latest row that
 * carries an action link and names the NPC's persona as a target, unless that persona
 * has posted since. A plain targeted pose does not count.
 */
export function pendingNpcResponse(
  interactions: Interaction[],
  npcPersonaId: number
): Interaction | null {
  for (let i = interactions.length - 1; i >= 0; i--) {
    const row = interactions[i];
    if (row.persona.id === npcPersonaId) return null;
    const hasAction = (row.action_links?.length ?? 0) > 0;
    if (hasAction && row.target_persona_ids.includes(npcPersonaId)) return row;
  }
  return null;
}
