import { describe, it, expect } from 'vitest';
import { sessionAttention } from './attention';
import type { Session } from '@/store/gameSlice';
import type { InteractionWsPayload } from '@/hooks/types';

const VIEWER_PERSONA_ID = 10;

function makeInteraction(overrides: Partial<InteractionWsPayload> = {}): InteractionWsPayload {
  return {
    id: 1,
    persona: { id: 99, name: 'Other', thumbnail_url: '' },
    content: 'Hello',
    mode: 'say',
    timestamp: '2026-01-01T00:00:00Z',
    scene_id: 1,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    ...overrides,
  };
}

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    isConnected: true,
    messages: [],
    unread: 0,
    commands: [],
    room: null,
    scene: null,
    sceneInteractions: [],
    threadLastSeen: {},
    sceneBaselineId: 0,
    openThreadTabs: [],
    activeThreadTab: null,
    ...overrides,
  };
}

describe('sessionAttention', () => {
  it('counts a whisper to me as direct', () => {
    const session = makeSession({
      sceneInteractions: [
        makeInteraction({
          id: 5,
          mode: 'whisper',
          persona: { id: 99, name: 'Other', thumbnail_url: '' },
          receiver_persona_ids: [VIEWER_PERSONA_ID],
        }),
      ],
    });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 1, ambient: false });
  });

  it('counts room scroll as ambient, not direct', () => {
    const session = makeSession({
      sceneInteractions: [makeInteraction({ id: 5, mode: 'say' })],
    });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 0, ambient: true });
  });

  it('counts an own-authored whisper as neither direct nor ambient', () => {
    const session = makeSession({
      sceneInteractions: [
        makeInteraction({
          id: 5,
          mode: 'whisper',
          persona: { id: VIEWER_PERSONA_ID, name: 'Me', thumbnail_url: '' },
          receiver_persona_ids: [99],
        }),
      ],
    });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 0, ambient: false });
  });

  it('counts a target thread that includes me as direct', () => {
    const session = makeSession({
      sceneInteractions: [
        makeInteraction({
          id: 5,
          mode: 'say',
          persona: { id: 99, name: 'Other', thumbnail_url: '' },
          target_persona_ids: [VIEWER_PERSONA_ID, 42],
        }),
      ],
    });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 1, ambient: false });
  });

  it('clears direct once threadLastSeen marks the whisper thread read', () => {
    const interaction = makeInteraction({
      id: 5,
      mode: 'whisper',
      persona: { id: 99, name: 'Other', thumbnail_url: '' },
      receiver_persona_ids: [VIEWER_PERSONA_ID],
    });
    const sortedIds = [interaction.persona.id, VIEWER_PERSONA_ID].sort((a, b) => a - b);
    const threadKey = `whisper:${sortedIds.join(',')}`;
    const session = makeSession({
      sceneInteractions: [interaction],
      threadLastSeen: { [threadKey]: 5 },
    });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 0, ambient: false });
  });

  it('a target thread NOT aimed at me is ambient, not direct', () => {
    const session = makeSession({
      sceneInteractions: [
        makeInteraction({
          id: 5,
          mode: 'say',
          persona: { id: 99, name: 'Other', thumbnail_url: '' },
          target_persona_ids: [42, 43],
        }),
      ],
    });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 0, ambient: true });
  });

  it('falls back to the legacy unread scalar for ambient', () => {
    const session = makeSession({ unread: 3 });

    const result = sessionAttention(session, VIEWER_PERSONA_ID);

    expect(result).toEqual({ direct: 0, ambient: true });
  });

  it('routes a whisper to ambient (not direct) when personaId is null (pre-roster-load flicker guard)', () => {
    const session = makeSession({
      sceneInteractions: [
        makeInteraction({
          id: 5,
          mode: 'whisper',
          persona: { id: 99, name: 'Other', thumbnail_url: '' },
          receiver_persona_ids: [1],
        }),
      ],
    });

    const result = sessionAttention(session, null);

    expect(result).toEqual({ direct: 0, ambient: true });
  });
});
