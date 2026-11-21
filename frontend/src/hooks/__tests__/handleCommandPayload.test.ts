/**
 * Tests for handleCommandPayload: the `commands` frame writes the names the
 * character can type (#4346) to the store and nothing else.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleCommandPayload } from '../handleCommandPayload';
import { setSessionCommandNames } from '@/store/gameSlice';
import { store } from '@/store/store';

vi.mock('@/store/store', () => ({
  store: {
    dispatch: vi.fn(),
  },
}));

vi.mock('@/store/gameSlice', () => ({
  setSessionCommandNames: vi.fn((payload) => ({ type: 'game/setSessionCommandNames', payload })),
}));

describe('handleCommandPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('dispatches the frame kwargs names for the character', () => {
    handleCommandPayload('TestCharacter', { names: ['desc', 'friend', 'who'] });

    expect(setSessionCommandNames).toHaveBeenCalledWith({
      character: 'TestCharacter',
      commandNames: ['desc', 'friend', 'who'],
    });
    expect(store.dispatch).toHaveBeenCalledWith({
      type: 'game/setSessionCommandNames',
      payload: { character: 'TestCharacter', commandNames: ['desc', 'friend', 'who'] },
    });
  });

  it('clears the names when the frame carries none', () => {
    handleCommandPayload('TestCharacter', {});
    handleCommandPayload('TestCharacter');

    expect(setSessionCommandNames).toHaveBeenNthCalledWith(1, {
      character: 'TestCharacter',
      commandNames: [],
    });
    expect(setSessionCommandNames).toHaveBeenNthCalledWith(2, {
      character: 'TestCharacter',
      commandNames: [],
    });
  });

  it('keeps only the strings from a malformed list', () => {
    handleCommandPayload('TestCharacter', { names: ['who', 7, null, 'pose'] });

    expect(setSessionCommandNames).toHaveBeenCalledWith({
      character: 'TestCharacter',
      commandNames: ['who', 'pose'],
    });
  });
});
