import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useThreading, getThreadKey } from '../useThreading';
import type { Interaction } from '../../types';

function makeInteraction(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 1,
    persona: { id: 10, name: 'Alice' },
    content: 'Hello',
    mode: 'say',
    visibility: 'default',
    timestamp: '2026-01-01T00:00:00Z',
    scene: 1,
    reactions: [],
    is_favorited: false,
    target_persona_names: [],
    place: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    ...overrides,
  };
}

describe('getThreadKey', () => {
  it('returns "room" for a basic interaction', () => {
    expect(getThreadKey(makeInteraction())).toBe('room');
  });

  it('returns whisper key with sorted receiver IDs', () => {
    const i = makeInteraction({
      mode: 'whisper',
      receiver_persona_ids: [5, 2, 8],
    });
    expect(getThreadKey(i)).toBe('whisper:2,5,8');
  });

  it('returns place key for place interactions', () => {
    const i = makeInteraction({ place: 42, place_name: 'Balcony' });
    expect(getThreadKey(i)).toBe('place:42');
  });

  it('returns target key with sorted target IDs', () => {
    const i = makeInteraction({ target_persona_ids: [9, 3] });
    expect(getThreadKey(i)).toBe('target:3,9');
  });

  it('whisper takes precedence over place', () => {
    const i = makeInteraction({
      mode: 'whisper',
      receiver_persona_ids: [1],
      place: 5,
    });
    expect(getThreadKey(i)).toBe('whisper:1');
  });

  it('place takes precedence over target', () => {
    const i = makeInteraction({
      place: 5,
      target_persona_ids: [1, 2],
    });
    expect(getThreadKey(i)).toBe('place:5');
  });
});

describe('useThreading', () => {
  it('groups room-wide interactions into "room" thread', () => {
    const interactions = [makeInteraction({ id: 1 }), makeInteraction({ id: 2 })];

    const { result } = renderHook(() => useThreading(interactions, 'Grand Hall'));

    expect(result.current.threads).toHaveLength(1);
    expect(result.current.threads[0].key).toBe('room');
    expect(result.current.threads[0].type).toBe('room');
    expect(result.current.threads[0].label).toBe('Grand Hall');
  });

  it('groups place interactions by place ID', () => {
    const interactions = [
      makeInteraction({ id: 1, place: 10, place_name: 'Balcony' }),
      makeInteraction({ id: 2, place: 10, place_name: 'Balcony' }),
      makeInteraction({ id: 3, place: 20, place_name: 'Garden' }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    const placeThreads = result.current.threads.filter((t) => t.type === 'place');
    expect(placeThreads).toHaveLength(2);
    expect(placeThreads.map((t) => t.key).sort()).toEqual(['place:10', 'place:20']);
  });

  it('groups whispers by sorted receiver IDs', () => {
    const interactions = [
      makeInteraction({ id: 1, mode: 'whisper', receiver_persona_ids: [2, 5] }),
      makeInteraction({ id: 2, mode: 'whisper', receiver_persona_ids: [5, 2] }),
      makeInteraction({ id: 3, mode: 'whisper', receiver_persona_ids: [3] }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    const whisperThreads = result.current.threads.filter((t) => t.type === 'whisper');
    expect(whisperThreads).toHaveLength(2);
  });

  it('groups targeted interactions by sorted target IDs', () => {
    const interactions = [
      makeInteraction({ id: 1, target_persona_ids: [3, 1] }),
      makeInteraction({ id: 2, target_persona_ids: [1, 3] }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    const targetThreads = result.current.threads.filter((t) => t.type === 'target');
    expect(targetThreads).toHaveLength(1);
    expect(targetThreads[0].key).toBe('target:1,3');
  });

  it('filtering: toggling a thread hides/shows its interactions', () => {
    const interactions = [
      makeInteraction({ id: 1 }),
      makeInteraction({ id: 2, place: 5, place_name: 'Alcove' }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    // Initially all visible
    expect(result.current.filteredInteractions).toHaveLength(2);

    // Toggle place thread on — now only place thread visible
    act(() => {
      result.current.toggleThreadVisibility('place:5');
    });

    expect(result.current.filteredInteractions).toHaveLength(1);
    expect(result.current.filteredInteractions[0].id).toBe(2);
  });

  it('filtering: "show all" resets to unfiltered', () => {
    const interactions = [
      makeInteraction({ id: 1 }),
      makeInteraction({ id: 2, place: 5, place_name: 'Alcove' }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    act(() => {
      result.current.toggleThreadVisibility('place:5');
    });
    expect(result.current.filteredInteractions).toHaveLength(1);

    act(() => {
      result.current.showAll();
    });
    expect(result.current.filteredInteractions).toHaveLength(2);
  });

  it('per-persona hiding removes a specific persona interactions', () => {
    const interactions = [
      makeInteraction({ id: 1, persona: { id: 10, name: 'Alice' } }),
      makeInteraction({ id: 2, persona: { id: 20, name: 'Bob' } }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    act(() => {
      result.current.togglePersonaHidden('room', 10);
    });

    expect(result.current.filteredInteractions).toHaveLength(1);
    expect(result.current.filteredInteractions[0].persona.name).toBe('Bob');
  });

  it('thread labels use room name for room thread', () => {
    const interactions = [makeInteraction()];
    const { result } = renderHook(() => useThreading(interactions, 'The Grand Ballroom'));

    expect(result.current.threads[0].label).toBe('The Grand Ballroom');
  });

  it('thread labels use place name for place threads', () => {
    const interactions = [makeInteraction({ id: 1, place: 7, place_name: 'The Balcony' })];
    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    const placeThread = result.current.threads.find((t) => t.type === 'place');
    expect(placeThread?.label).toBe('The Balcony');
  });

  it('persona names truncated at 3 with "..."', () => {
    const interactions = [
      makeInteraction({ id: 1, target_persona_ids: [1, 2, 3, 4], persona: { id: 10, name: 'A' } }),
      makeInteraction({ id: 2, target_persona_ids: [1, 2, 3, 4], persona: { id: 20, name: 'B' } }),
      makeInteraction({ id: 3, target_persona_ids: [1, 2, 3, 4], persona: { id: 30, name: 'C' } }),
      makeInteraction({ id: 4, target_persona_ids: [1, 2, 3, 4], persona: { id: 40, name: 'D' } }),
    ];

    const { result } = renderHook(() => useThreading(interactions, 'Room'));

    const targetThread = result.current.threads.find((t) => t.type === 'target');
    expect(targetThread?.label).toBe('A, B, C...');
  });

  it('getHiddenPersonaIds returns empty set for unknown thread', () => {
    const { result } = renderHook(() => useThreading([], 'Room'));
    const hidden = result.current.getHiddenPersonaIds('nonexistent');
    expect(hidden.size).toBe(0);
  });
});
