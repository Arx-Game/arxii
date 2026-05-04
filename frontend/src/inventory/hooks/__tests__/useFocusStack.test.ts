import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { useFocusStack, type FocusEntry } from '../useFocusStack';

const ROOM_ENTRY: FocusEntry = {
  kind: 'room',
  room: { dbref: '#42', name: 'Test Room', thumbnail_url: null, commands: [], description: '' },
  sceneSummary: null,
};

const CHARACTER_ENTRY: FocusEntry = {
  kind: 'character',
  character: { id: 1, name: 'Alice' },
};

const ITEM_ENTRY: FocusEntry = {
  kind: 'item',
  item: { id: 7, name: 'Pearl Necklace' },
};

describe('useFocusStack', () => {
  it('starts with the provided initial entry as current', () => {
    const { result } = renderHook(() => useFocusStack(ROOM_ENTRY));
    expect(result.current.current).toEqual(ROOM_ENTRY);
    expect(result.current.depth).toBe(1);
  });

  it('push appends and updates current', () => {
    const { result } = renderHook(() => useFocusStack(ROOM_ENTRY));
    act(() => {
      result.current.push(CHARACTER_ENTRY);
    });
    expect(result.current.current).toEqual(CHARACTER_ENTRY);
    expect(result.current.depth).toBe(2);
  });

  it('multiple pushes stack correctly', () => {
    const { result } = renderHook(() => useFocusStack(ROOM_ENTRY));
    act(() => {
      result.current.push(CHARACTER_ENTRY);
      result.current.push(ITEM_ENTRY);
    });
    expect(result.current.current).toEqual(ITEM_ENTRY);
    expect(result.current.depth).toBe(3);
  });

  it('pop returns to previous entry', () => {
    const { result } = renderHook(() => useFocusStack(ROOM_ENTRY));
    act(() => {
      result.current.push(CHARACTER_ENTRY);
      result.current.push(ITEM_ENTRY);
    });
    act(() => {
      result.current.pop();
    });
    expect(result.current.current).toEqual(CHARACTER_ENTRY);
    expect(result.current.depth).toBe(2);
  });

  it('pop at depth 1 is a no-op (always preserves a focus)', () => {
    const { result } = renderHook(() => useFocusStack(ROOM_ENTRY));
    act(() => {
      result.current.pop();
    });
    expect(result.current.current).toEqual(ROOM_ENTRY);
    expect(result.current.depth).toBe(1);
  });

  it('reset replaces the entire stack with a single entry', () => {
    const { result } = renderHook(() => useFocusStack(ROOM_ENTRY));
    act(() => {
      result.current.push(CHARACTER_ENTRY);
      result.current.push(ITEM_ENTRY);
    });
    act(() => {
      result.current.reset(ROOM_ENTRY);
    });
    expect(result.current.current).toEqual(ROOM_ENTRY);
    expect(result.current.depth).toBe(1);
  });
});
