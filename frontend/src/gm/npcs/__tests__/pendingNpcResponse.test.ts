import { describe, expect, it } from 'vitest';

import type { Interaction } from '@/scenes/types';

import { pendingNpcResponse } from '../pendingNpcResponse';

const NPC = 70;
function row(id: number, personaId: number, targets: number[], withAction: boolean) {
  return {
    id,
    persona: { id: personaId, name: `P${personaId}` },
    content: 'x',
    target_persona_ids: targets,
    action_links: withAction
      ? [
          {
            id,
            ordering: 0,
            action_interaction: { id, content: 'a', mode: 'action', timestamp: '' },
          },
        ]
      : [],
  } as unknown as Interaction;
}

describe('pendingNpcResponse', () => {
  it('returns the latest action aimed at the NPC', () => {
    const rows = [row(1, 5, [NPC], true), row(2, 6, [NPC], true)];
    expect(pendingNpcResponse(rows, NPC)?.id).toBe(2);
  });
  it('ignores a plain targeted pose', () => {
    expect(pendingNpcResponse([row(1, 5, [NPC], false)], NPC)).toBeNull();
  });
  it('ignores an action aimed at someone else', () => {
    expect(pendingNpcResponse([row(1, 5, [99], true)], NPC)).toBeNull();
  });
  it('clears once the NPC persona posts after it', () => {
    const rows = [row(1, 5, [NPC], true), row(2, NPC, [], false)];
    expect(pendingNpcResponse(rows, NPC)).toBeNull();
  });
});
