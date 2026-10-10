import { describe, expect, it } from 'vitest';
import type { FeedNote } from '@/hooks/types';
import type { Interaction } from '@/scenes/types';
import type { Thread } from '@/scenes/hooks/useThreading';
import { allRailRows, buildRailRows, isPageRowKey, pageRowKey } from './railRows';

function thread(overrides: Partial<Thread>): Thread {
  return {
    key: 'room',
    type: 'room',
    label: 'Quiet courtyard',
    participantPersonas: [],
    latestTimestamp: '2026-01-01T00:00:00Z',
    unreadCount: 0,
    ...overrides,
  };
}

function ambient(overrides: Partial<Interaction> & { id: number }): Interaction {
  return {
    persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
    content: 'leans in.',
    mode: 'whisper',
    timestamp: '2026-01-01T00:05:00Z',
    scene: null,
    place: null,
    place_name: null,
    receiver_persona_ids: [7],
    target_persona_ids: [],
    ...overrides,
  } as Interaction;
}

const base = {
  threads: [] as Thread[],
  ambientInteractions: [] as Interaction[],
  notes: [] as FeedNote[],
  roomName: 'Quiet courtyard',
  viewerPersonaId: 7,
  lastSeenByThread: {},
  sceneBaselineId: null,
};

describe('buildRailRows', () => {
  it('always draws the room row first, from the room name when nothing has been said', () => {
    const groups = buildRailRows(base);
    expect(groups.here.map((row) => row.key)).toEqual(['room']);
    expect(groups.here[0]).toMatchObject({ kind: 'room', label: 'Quiet courtyard', person: null });
    expect(groups.pages).toEqual([]);
  });

  it('names a whisper row after the other party, with their face, newest first', () => {
    const groups = buildRailRows({
      ...base,
      threads: [
        thread({}),
        thread({
          key: 'whisper:7,99',
          type: 'whisper',
          label: 'Whisper: Tehom, Nyx',
          participantPersonas: [
            { id: 7, name: 'Tehom', thumbnailUrl: null },
            { id: 99, name: 'Nyx', thumbnailUrl: '/nyx.png' },
          ],
          latestTimestamp: '2026-01-01T00:02:00Z',
          unreadCount: 1,
        }),
        thread({
          key: 'place:4',
          type: 'place',
          label: 'The long table',
          latestTimestamp: '2026-01-01T00:03:00Z',
          unreadCount: 2,
        }),
      ],
    });
    expect(groups.here.map((row) => [row.key, row.kind, row.label])).toEqual([
      ['room', 'room', 'Quiet courtyard'],
      ['place:4', 'place', 'The long table'],
      ['whisper:7,99', 'whisper', 'Nyx'],
    ]);
    expect(groups.here[2].person).toEqual({ id: 99, name: 'Nyx', thumbnailUrl: '/nyx.png' });
    expect(groups.here[1].person).toBeNull();
  });

  it("groups the quiet room's ambient interactions the same way and counts them unread until read", () => {
    const groups = buildRailRows({
      ...base,
      ambientInteractions: [
        ambient({ id: 40 }),
        ambient({ id: 41, timestamp: '2026-01-01T00:06:00Z' }),
      ],
    });
    expect(groups.here.map((row) => row.key)).toEqual(['room', 'whisper:7,99']);
    expect(groups.here[1]).toMatchObject({ kind: 'whisper', label: 'Nyx', unreadCount: 2 });
    const read = buildRailRows({
      ...base,
      ambientInteractions: [ambient({ id: 40 }), ambient({ id: 41 })],
      lastSeenByThread: { 'whisper:7,99': 41 },
    });
    expect(read.here[1].unreadCount).toBe(0);
  });

  it('merges a conversation the scene and the quiet room both hold into one row', () => {
    const groups = buildRailRows({
      ...base,
      threads: [
        thread({
          key: 'whisper:7,99',
          type: 'whisper',
          label: 'Whisper: Nyx',
          participantPersonas: [{ id: 99, name: 'Nyx', thumbnailUrl: null }],
          latestTimestamp: '2026-01-01T00:02:00Z',
          unreadCount: 1,
        }),
      ],
      ambientInteractions: [ambient({ id: 40 })],
    });
    expect(groups.here.filter((row) => row.key === 'whisper:7,99')).toHaveLength(1);
    expect(groups.here[1]).toMatchObject({
      unreadCount: 2,
      latestTimestamp: '2026-01-01T00:05:00Z',
    });
  });

  it("lists pages per correspondent, counting their lines and never the viewer's echo", () => {
    const notes: FeedNote[] = [
      {
        id: 'n1',
        kind: 'page',
        content: 'Bram pages: Sunday?',
        from: { personaId: 31, name: 'Bram' },
        timestamp: '2026-01-01T00:07:00Z',
      },
      {
        id: 'n2',
        kind: 'page',
        content: 'You page Bram: Yes.',
        from: { personaId: 31, name: 'Bram' },
        outgoing: true,
        timestamp: '2026-01-01T00:08:00Z',
      },
      { id: 'n3', kind: 'look', content: 'A courtyard.', timestamp: '2026-01-01T00:09:00Z' },
    ];
    const groups = buildRailRows({ ...base, notes });
    expect(groups.pages).toHaveLength(1);
    expect(groups.pages[0]).toMatchObject({
      key: 'page:31',
      kind: 'page',
      label: 'Bram',
      unreadCount: 1,
      latestTimestamp: '2026-01-01T00:08:00Z',
    });
    const read = buildRailRows({
      ...base,
      notes,
      lastSeenByThread: { 'page:31': Date.parse('2026-01-01T00:07:30Z') },
    });
    expect(read.pages[0].unreadCount).toBe(0);
    expect(allRailRows(groups).map((row) => row.key)).toEqual(['room', 'page:31']);
  });

  it('names a page row key by the correspondent persona', () => {
    expect(pageRowKey(31)).toBe('page:31');
    expect(isPageRowKey('page:31')).toBe(true);
    expect(isPageRowKey('whisper:1,2')).toBe(false);
    expect(isPageRowKey(null)).toBe(false);
  });
});
