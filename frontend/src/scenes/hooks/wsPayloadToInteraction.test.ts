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

  // #4101 Task 11 fix round 1, item 11: the WS payload's `narrates` must map
  // through, including the no-subject shape (a stake outcome, or a subject
  // this payload cannot name).
  it('maps narrates through as-is', () => {
    const withNarrates: InteractionWsPayload = {
      ...payload,
      narrates: {
        prompt_id: 7,
        kind: 'crossing',
        kind_label: 'Crossing',
        subject_name: 'Rowan Ashcombe',
        subject_persona_id: 30,
      },
    };
    expect(wsPayloadToInteraction(withNarrates).narrates).toEqual({
      prompt_id: 7,
      kind: 'crossing',
      kind_label: 'Crossing',
      subject_name: 'Rowan Ashcombe',
      subject_persona_id: 30,
    });
  });

  it('maps narrates with no subject (a stake outcome) through with the keys absent', () => {
    const noSubject: InteractionWsPayload = {
      ...payload,
      narrates: { prompt_id: 9, kind: 'stake_outcome', kind_label: 'Stake outcome' },
    };
    const row = wsPayloadToInteraction(noSubject);
    expect(row.narrates).toEqual({
      prompt_id: 9,
      kind: 'stake_outcome',
      kind_label: 'Stake outcome',
    });
    expect(row.narrates).not.toHaveProperty('subject_name');
    expect(row.narrates).not.toHaveProperty('subject_persona_id');
  });

  it('defaults narrates to null when the payload carries none', () => {
    expect(wsPayloadToInteraction(payload).narrates).toBeNull();
  });
});
