import { describe, expect, it } from 'vitest';
import type { FeedNote } from '@/hooks/types';
import { interleaveNotes } from './feedRows';

const note = (id: string, timestamp: string): FeedNote => ({
  id,
  kind: 'look',
  content: id,
  timestamp,
});

describe('interleaveNotes (#3856)', () => {
  it('orders items and notes together by time, items first on a tie', () => {
    const rows = interleaveNotes(
      [
        { key: 'a', timestamp: '2026-09-14T22:00:10Z' },
        { key: 'b', timestamp: '2026-09-14T22:00:30Z' },
      ],
      [note('n1', '2026-09-14T22:00:20.000Z'), note('n2', '2026-09-14T22:00:30.000Z')]
    );

    expect(rows.map((row) => (row.type === 'note' ? row.note.id : row.item.key))).toEqual([
      'a',
      'n1',
      'b',
      'n2',
    ]);
  });

  it('compares by parsed time, so a server timestamp without milliseconds sorts correctly', () => {
    const rows = interleaveNotes(
      [{ key: 'later', timestamp: '2026-09-14T22:00:01Z' }],
      [note('earlier', '2026-09-14T22:00:00.500Z')]
    );

    expect(rows.map((row) => (row.type === 'note' ? row.note.id : row.item.key))).toEqual([
      'earlier',
      'later',
    ]);
  });

  it('keeps the given order of items with the same time', () => {
    const rows = interleaveNotes(
      [
        { key: 'first', timestamp: '2026-09-14T22:00:00Z' },
        { key: 'second', timestamp: '2026-09-14T22:00:00Z' },
      ],
      []
    );

    expect(rows.map((row) => (row.type === 'note' ? row.note.id : row.item.key))).toEqual([
      'first',
      'second',
    ]);
  });

  it('puts a note with an unreadable timestamp at the end rather than dropping it', () => {
    const rows = interleaveNotes(
      [{ key: 'a', timestamp: '2026-09-14T22:00:00Z' }],
      [note('odd', 'not a time')]
    );

    expect(rows.map((row) => (row.type === 'note' ? row.note.id : row.item.key))).toEqual([
      'a',
      'odd',
    ]);
  });
});
