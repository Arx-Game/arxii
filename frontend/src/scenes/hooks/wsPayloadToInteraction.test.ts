import { describe, expect, it } from 'vitest';
import type { InteractionWsPayload } from '@/hooks/types';
import { wsPayloadToInteraction } from './useSceneInteractions';

const payload: InteractionWsPayload = {
  id: 901,
  persona: { id: 18, name: 'Tehom', thumbnail_url: '' },
  content: 'stops at the edge of the plaza.',
  line: 'Tehom stops at the edge of the plaza.',
  mode: 'pose',
  timestamp: '2026-09-15T02:01:00Z',
  scene_id: 1,
  place_id: null,
  place_name: null,
  receiver_persona_ids: [],
  target_persona_ids: [],
};

describe('wsPayloadToInteraction (#3858)', () => {
  it('carries the rendered line beside the raw content', () => {
    const row = wsPayloadToInteraction(payload);
    expect(row.content).toBe('stops at the edge of the plaza.');
    expect(row.line).toBe('Tehom stops at the edge of the plaza.');
  });

  it('leaves the line absent when the server sent none', () => {
    const { line: _line, ...older } = payload;
    expect(wsPayloadToInteraction(older).line).toBeUndefined();
  });
});
