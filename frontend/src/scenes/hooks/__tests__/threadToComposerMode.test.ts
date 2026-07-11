import { describe, expect, it } from 'vitest';
import { tabKeyToComposerMode } from '../threadToComposerMode';
import type { Thread } from '../useThreading';

const whisperThread: Thread = {
  key: 'whisper:1,2',
  type: 'whisper',
  label: 'Whisper: Alise, Ben',
  participantPersonas: [
    { id: 1, name: 'Alise' },
    { id: 2, name: 'Ben' },
  ],
  latestTimestamp: '2026-07-11T00:00:00Z',
  unreadCount: 0,
};

describe('tabKeyToComposerMode (#2165)', () => {
  it('derives a locked whisper mode from a resolved thread', () => {
    const mode = tabKeyToComposerMode('whisper:1,2', [whisperThread], 'The Grand Ballroom');
    expect(mode.command).toBe('whisper');
    expect(mode.targets).toEqual(['Alise', 'Ben']);
    expect(mode.locked).toBe(true);
  });

  it('falls back to a target-less locked whisper for an unresolved whisper key', () => {
    const mode = tabKeyToComposerMode('whisper:3,4', [], 'The Grand Ballroom');
    expect(mode.command).toBe('whisper');
    expect(mode.targets).toEqual([]);
    expect(mode.locked).toBe(true);
  });

  it('falls back to locked tabletalk for an unresolved place key', () => {
    const mode = tabKeyToComposerMode('place:7', [], 'The Grand Ballroom');
    expect(mode.command).toBe('tt');
    expect(mode.locked).toBe(true);
  });
});
