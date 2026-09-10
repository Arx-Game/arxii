import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadPlayPreferences,
  DEFAULT_PLAY_PREFERENCES,
  loadConversationAnchor,
  saveConversationAnchor,
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
      anchor: { poseId: '42', threadId: 'thread-a', offsetPx: 120 },
      collapsed: ['thread-b'],
    });
    expect(loadConversationAnchor('scene:1')).toEqual({
      anchor: { poseId: '42', threadId: 'thread-a', offsetPx: 120 },
      collapsed: ['thread-b'],
    });
  });

  it('returns null for an unknown conversation', () => {
    expect(loadConversationAnchor('scene:999')).toBeNull();
  });

  it('evicts the oldest entry once 100 conversations are stored', () => {
    for (let i = 0; i < 100; i++) {
      saveConversationAnchor(`scene:${i}`, { anchor: null, collapsed: [] });
    }
    saveConversationAnchor('scene:100', { anchor: null, collapsed: [] });
    expect(loadConversationAnchor('scene:0')).toBeNull();
    expect(loadConversationAnchor('scene:100')).not.toBeNull();
  });
});
