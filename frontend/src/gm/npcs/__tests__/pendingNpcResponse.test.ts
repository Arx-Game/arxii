import { describe, expect, it } from 'vitest';

import type { Interaction } from '@/scenes/types';

import { pendingNpcResponse } from '../pendingNpcResponse';

const NPC = 70;

// The shapes seen in real play: the resolved action row has mode `action`, targets the NPC
// and has no action_links; the player's pose carries the links and targets nobody.
function actionRow(id: number, personaId: number, targets: number[]): Interaction {
  return {
    id,
    persona: { id: personaId, name: `P${personaId}` },
    content: 'Ysmay attempts to persuade Sergeant Mira',
    mode: 'action',
    target_persona_ids: targets,
    action_links: [],
  } as unknown as Interaction;
}
function pose(id: number, personaId: number, targets: number[], linkedActions: number[] = []) {
  return {
    id,
    persona: { id: personaId, name: `P${personaId}` },
    content: 'pose',
    mode: 'pose',
    target_persona_ids: targets,
    action_links: linkedActions.map((a, ordering) => ({
      id: a,
      ordering,
      action_interaction: { id: a, content: 'x', mode: 'action', timestamp: '' },
    })),
  } as unknown as Interaction;
}

describe('pendingNpcResponse', () => {
  it('finds the resolved action row even though a later pose carries the links', () => {
    const rows = [actionRow(7, 5, [NPC]), actionRow(8, 5, [NPC]), pose(9, 5, [], [7, 8])];
    expect(pendingNpcResponse(rows, NPC)?.id).toBe(8);
  });
  it('ignores a plain targeted pose', () => {
    expect(pendingNpcResponse([pose(1, 5, [NPC])], NPC)).toBeNull();
  });
  it('ignores an action aimed at someone else', () => {
    expect(pendingNpcResponse([actionRow(1, 5, [99])], NPC)).toBeNull();
  });
  it('clears once the NPC persona posts after it', () => {
    expect(pendingNpcResponse([actionRow(1, 5, [NPC]), pose(2, NPC, [])], NPC)).toBeNull();
  });
});
