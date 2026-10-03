/**
 * Tests for WonOverRows — the won-over opponents on the outcome rail (#4091).
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { useDispatchPlayerAction } from '@/combat/queries';
import { createActionRequest } from '@/scenes/actionQueries';
import { WonOverRows } from '../components/WonOverRows';
import type { WonOverRow } from '../components/WonOverRows';

vi.mock('@/combat/queries', async () => {
  const actual = await vi.importActual<typeof import('@/combat/queries')>('@/combat/queries');
  return {
    ...actual,
    useDispatchPlayerAction: vi.fn(),
  };
});

vi.mock('@/scenes/actionQueries', async () => {
  const actual =
    await vi.importActual<typeof import('@/scenes/actionQueries')>('@/scenes/actionQueries');
  return {
    ...actual,
    createActionRequest: vi.fn(() => Promise.resolve({ status: 'resolved' })),
  };
});

const mockUseDispatchPlayerAction = vi.mocked(useDispatchPlayerAction);

function mockDispatch(mutate = vi.fn()) {
  mockUseDispatchPlayerAction.mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  return mutate;
}

const baseRow: WonOverRow = {
  opponent_id: 7,
  name: 'Road Bandit',
  verb: 'charmed',
  source_label: "Wren's Sweet Talk",
  nameless: true,
  persona_id: null,
  present: true,
  condition: null,
  holds_until_settled: true,
  strength: 3,
  can_bind: true,
  can_take_into_service: false,
  can_send_away: true,
  can_settle: false,
};

describe('WonOverRows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDispatch();
  });

  it('shows bind only when the viewer may bind', () => {
    renderWithProviders(<WonOverRows rows={[baseRow]} characterId={42} sceneId="1" />);

    expect(screen.getByText('Bind as companion')).toBeInTheDocument();
    // Nameless (ruling R2): never a Settle button, regardless of can_settle.
    expect(screen.queryByText('Settle')).not.toBeInTheDocument();
  });

  it('shows holds until settled for a rounds-measured hold', () => {
    renderWithProviders(
      <WonOverRows
        rows={[{ ...baseRow, holds_until_settled: true }]}
        characterId={42}
        sceneId="1"
      />
    );

    expect(screen.getByText(/holds until settled/)).toBeInTheDocument();
  });

  it('hides Bind for a row the viewer did not charm', () => {
    renderWithProviders(
      <WonOverRows rows={[{ ...baseRow, can_bind: false }]} characterId={42} sceneId="1" />
    );

    expect(screen.queryByText('Bind as companion')).not.toBeInTheDocument();
  });

  it('Send away dispatches send_away with the opponent id', async () => {
    const user = userEvent.setup();
    const mutate = mockDispatch();

    renderWithProviders(
      <WonOverRows rows={[{ ...baseRow, can_send_away: true }]} characterId={42} sceneId="1" />
    );

    await user.click(screen.getByText('Send away'));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        {
          ref: { backend: 'registry', registry_key: 'send_away' },
          kwargs: { combat_opponent_id: 7 },
        },
        expect.any(Object)
      );
    });
  });

  it('Settle posts a settle action request for a persona-backed row', async () => {
    const user = userEvent.setup();
    const namedRow: WonOverRow = {
      ...baseRow,
      nameless: false,
      persona_id: 99,
      can_bind: false,
      can_take_into_service: true,
      can_send_away: true,
      can_settle: true,
    };

    renderWithProviders(<WonOverRows rows={[namedRow]} characterId={42} sceneId="7" />);

    await user.click(screen.getByText('Settle'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith('7', {
        action_key: 'settle',
        target_persona_id: 99,
      });
    });
  });
});
