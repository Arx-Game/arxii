/**
 * The combat panel's action list carries the fighter's moves (#4607): YourTurn lists them
 * with the hops left, so a filter to COMBAT-backend actions alone left its move list empty.
 */
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PlayerAction } from '@/scenes/actionTypes';
import { useAvailableActions } from '../queries';

function action(backend: string, registryKey: string | null, name: string): PlayerAction {
  return {
    backend,
    display_name: name,
    description: '',
    prerequisite_met: true,
    prerequisite_reasons: [],
    ref: { backend, registry_key: registryKey },
  } as unknown as PlayerAction;
}

const results = [
  action('combat', null, 'Lunge'),
  action('registry', 'move_to_position', 'Move to Yard'),
  action('registry', 'take_flight', 'Take flight'),
  action('registry', 'land', 'Land'),
  action('registry', 'pass_held_ground', 'Get past Bandit into Gatehouse'),
  action('registry', 'take_position', 'Take position: Gate'),
  action('registry', 'create_battle', 'Create battle'),
];

vi.mock('@/scenes/actionQueries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/scenes/actionQueries')>();
  return {
    ...actual,
    useAvailableActionsQuery: () => ({
      data: { results },
      isLoading: false,
      isError: false,
    }),
  };
});

describe('useAvailableActions', () => {
  it('keeps the combat actions and the moves, and nothing else', () => {
    const { result } = renderHook(() => useAvailableActions(4));

    // Take-off, landing and the pass roll are moves too (#4663).
    expect(result.current.data.map((a) => a.display_name)).toEqual([
      'Lunge',
      'Move to Yard',
      'Take flight',
      'Land',
      'Get past Bandit into Gatehouse',
    ]);
  });
});
