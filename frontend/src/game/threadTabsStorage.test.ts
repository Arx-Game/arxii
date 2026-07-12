import { describe, it, expect, beforeEach } from 'vitest';
import { loadThreadTabs, saveThreadTabs, type StoredThreadTabs } from './threadTabsStorage';

describe('threadTabsStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('round-trips a value', () => {
    const value: StoredThreadTabs = {
      openThreadTabs: ['whisper:9', 'place:3'],
      activeThreadTab: 'whisper:9',
    };
    saveThreadTabs('Aria', '100', value);
    expect(loadThreadTabs('Aria', '100')).toEqual(value);
  });

  it('returns null when nothing is stored', () => {
    expect(loadThreadTabs('Aria', '100')).toBeNull();
  });

  it('returns null for garbage JSON', () => {
    localStorage.setItem('arx:threadTabs:Aria:100', 'not json{{{');
    expect(loadThreadTabs('Aria', '100')).toBeNull();
  });

  it('returns null when openThreadTabs is not an array', () => {
    localStorage.setItem(
      'arx:threadTabs:Aria:100',
      JSON.stringify({ openThreadTabs: 'whisper:9', activeThreadTab: null })
    );
    expect(loadThreadTabs('Aria', '100')).toBeNull();
  });

  it('prunes other scene keys for the same character, but leaves other characters alone', () => {
    saveThreadTabs('Aria', '100', { openThreadTabs: ['whisper:9'], activeThreadTab: 'whisper:9' });
    saveThreadTabs('Bianca', '200', {
      openThreadTabs: ['whisper:4'],
      activeThreadTab: 'whisper:4',
    });

    // Aria moves to a new scene — her old scene-100 entry should be pruned.
    saveThreadTabs('Aria', '300', { openThreadTabs: ['place:1'], activeThreadTab: null });

    expect(loadThreadTabs('Aria', '100')).toBeNull();
    expect(loadThreadTabs('Aria', '300')).toEqual({
      openThreadTabs: ['place:1'],
      activeThreadTab: null,
    });
    // Bianca's entry, a different character, is untouched.
    expect(loadThreadTabs('Bianca', '200')).toEqual({
      openThreadTabs: ['whisper:4'],
      activeThreadTab: 'whisper:4',
    });
  });
});
