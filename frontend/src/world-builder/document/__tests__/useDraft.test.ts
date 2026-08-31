import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';

import { useDraft } from '../useDraft';

describe('useDraft', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('starts from the remote value when no draft exists', () => {
    const { result } = renderHook(() => useDraft(1, 'description', 'server text'));
    expect(result.current.value).toBe('server text');
  });

  it('writes keystrokes to localStorage keyed by room+field', () => {
    const { result } = renderHook(() => useDraft(1, 'description', 'server text'));
    act(() => result.current.setValue('a work in progress'));

    expect(result.current.value).toBe('a work in progress');
    expect(window.localStorage.getItem('world-builder-draft:1:description')).toBe(
      'a work in progress'
    );
  });

  it('silently restores a draft left over from a previous mount', () => {
    window.localStorage.setItem('world-builder-draft:1:description', 'left mid-sentence');
    const { result } = renderHook(() => useDraft(1, 'description', 'server text'));
    expect(result.current.value).toBe('left mid-sentence');
  });

  it('keys drafts by room AND field — no bleed between rooms or fields', () => {
    window.localStorage.setItem('world-builder-draft:1:description', 'room one draft');
    const { result: nameResult } = renderHook(() => useDraft(1, 'name', 'The Foyer'));
    const { result: otherRoomResult } = renderHook(() => useDraft(2, 'description', 'other room'));

    expect(nameResult.current.value).toBe('The Foyer');
    expect(otherRoomResult.current.value).toBe('other room');
  });

  it('clearDraft removes the stored draft', () => {
    const { result } = renderHook(() => useDraft(1, 'description', 'server text'));
    act(() => result.current.setValue('typed text'));
    act(() => result.current.clearDraft());

    expect(window.localStorage.getItem('world-builder-draft:1:description')).toBeNull();
  });

  it('re-reads localStorage when roomId changes (switching rooms)', () => {
    window.localStorage.setItem('world-builder-draft:2:description', 'room two draft');
    const { result, rerender } = renderHook(
      ({ roomId, remote }: { roomId: number; remote: string }) =>
        useDraft(roomId, 'description', remote),
      { initialProps: { roomId: 1, remote: 'room one server text' } }
    );
    expect(result.current.value).toBe('room one server text');

    rerender({ roomId: 2, remote: 'room two server text' });
    expect(result.current.value).toBe('room two draft');
  });

  it('degrades to remoteValue when localStorage throws', () => {
    const spy = vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    const { result } = renderHook(() => useDraft(1, 'description', 'server text'));
    expect(result.current.value).toBe('server text');
    spy.mockRestore();
  });
});
