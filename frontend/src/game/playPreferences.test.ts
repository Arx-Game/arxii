import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadPlayPreferences,
  DEFAULT_PLAY_PREFERENCES,
  loadConversationAnchor,
  saveConversationAnchor,
  usePlayPreferences,
} from './playPreferences';

describe('playPreferences', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults new fields sensibly', () => {
    const prefs = loadPlayPreferences();
    expect(prefs.sidebarSide).toBe(DEFAULT_PLAY_PREFERENCES.sidebarSide);
    expect(prefs.readerMode).toBe(DEFAULT_PLAY_PREFERENCES.readerMode);
    expect(prefs.density).toBe(DEFAULT_PLAY_PREFERENCES.density);
    expect(prefs.sidebarSide).toBe('right');
    expect(prefs.readerMode).toBe('threads');
    expect(prefs.density).toBe('compact');
  });

  it('round-trips a conversation anchor', () => {
    saveConversationAnchor('scene:1', {
      anchors: {
        threads: { poseId: '42', threadId: 'thread-a', offsetPx: 120 },
        chronological: null,
      },
      collapsed: ['thread-b'],
    });
    expect(loadConversationAnchor('scene:1')).toEqual({
      anchors: {
        threads: { poseId: '42', threadId: 'thread-a', offsetPx: 120 },
        chronological: null,
      },
      collapsed: ['thread-b'],
    });
  });

  it('returns null for an unknown conversation', () => {
    expect(loadConversationAnchor('scene:999')).toBeNull();
  });

  it('keeps Threads and Chronological anchors in independent slots (#3759 review finding I5)', () => {
    saveConversationAnchor('scene:1', {
      anchors: {
        threads: { poseId: '1', threadId: null, offsetPx: 0 },
        chronological: { poseId: '2', threadId: null, offsetPx: 0 },
      },
      collapsed: [],
    });
    const stored = loadConversationAnchor('scene:1');
    expect(stored?.anchors.threads?.poseId).toBe('1');
    expect(stored?.anchors.chronological?.poseId).toBe('2');
  });

  it('evicts the oldest entry once 100 conversations are stored', () => {
    for (let i = 0; i < 100; i++) {
      saveConversationAnchor(`scene:${i}`, {
        anchors: { threads: null, chronological: null },
        collapsed: [],
      });
    }
    saveConversationAnchor('scene:100', {
      anchors: { threads: null, chronological: null },
      collapsed: [],
    });
    expect(loadConversationAnchor('scene:0')).toBeNull();
    expect(loadConversationAnchor('scene:100')).not.toBeNull();
  });

  it('treats a corrupted `entries: null` anchor store as empty instead of throwing', () => {
    localStorage.setItem('arx:play-anchors:v1', JSON.stringify({ order: [], entries: null }));
    expect(() => loadConversationAnchor('scene:1')).not.toThrow();
    expect(loadConversationAnchor('scene:1')).toBeNull();
  });

  it("does not let two independent usePlayPreferences() instances clobber each other's writes", () => {
    // DisplaySettings.tsx and ThreadedNarrativeReader.tsx each call
    // usePlayPreferences() independently, so each holds its own local
    // useState snapshot of the persisted blob from its own mount time. If
    // `update` merges a patch over that stale `current` snapshot instead of
    // a fresh read from storage, whichever instance writes second reverts
    // whatever the other instance had just set.
    const first = renderHook(() => usePlayPreferences());
    const second = renderHook(() => usePlayPreferences());

    act(() => {
      first.result.current.update({ readerMode: 'chronological' });
    });
    act(() => {
      second.result.current.update({ proseSize: 18 });
    });

    const persisted = loadPlayPreferences();
    expect(persisted.readerMode).toBe('chronological');
    expect(persisted.proseSize).toBe(18);
  });
});
