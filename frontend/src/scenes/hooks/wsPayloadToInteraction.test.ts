import { describe, expect, it } from 'vitest';
import type { InteractionWsPayload } from '@/hooks/types';
import { poseCarryingAction } from '@/gm/npcs/pendingNpcResponse';
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

  it('uses pushed endorsable resonances and pose kind', () => {
    const row = wsPayloadToInteraction({
      ...payload,
      pose_kind: 'entry',
      endorsable_resonances: [{ id: 4, name: 'Ember' }],
    });
    expect(row.pose_kind).toBe('entry');
    expect(row.endorsable_resonances).toEqual([{ id: 4, name: 'Ember' }]);
  });

  it('falls back for a payload without feed fields', () => {
    const row = wsPayloadToInteraction(payload);
    expect(row.pose_kind).toBe('standard');
    expect(row.endorsable_resonances).toEqual([]);
    expect(row.entry_endorsed_by_me).toBe(false);
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

// A live pose frame shaped as the backend journey test builds it (interaction_services
// serializes the pose's cached links the way the REST feed's action_links does).
describe('wsPayloadToInteraction action_links (#4418)', () => {
  const actionRow = wsPayloadToInteraction({
    ...payload,
    id: 900,
    mode: 'action',
    content: 'Ysmay attempts to persuade Captain Vael',
    target_persona_ids: [70],
    action_links: [],
  });
  const poseFrame: InteractionWsPayload = {
    ...payload,
    id: 902,
    persona: { id: 5, name: 'Ysmay', thumbnail_url: '' },
    content: 'holds up the forged orders.',
    action_links: [
      {
        id: 31,
        ordering: 0,
        action_interaction: {
          id: 900,
          content: 'Ysmay attempts to persuade Captain Vael',
          mode: 'action',
          timestamp: '2026-09-15T02:00:30Z',
        },
        has_critical_effect: false,
      },
    ],
  };

  it('keeps the links the pose carries on the stored row', () => {
    const row = wsPayloadToInteraction(poseFrame);
    expect(row.action_links).toHaveLength(1);
    expect(row.action_links?.[0].action_interaction.id).toBe(900);
  });

  it('gives a frame from before the field, or another mode, an empty list', () => {
    expect(wsPayloadToInteraction(payload).action_links).toEqual([]);
  });

  it('lets the NPC response card find the pose that carried the action', () => {
    const pose = wsPayloadToInteraction(poseFrame);
    expect(poseCarryingAction([actionRow, pose], actionRow)).toBe(pose);
  });
});
