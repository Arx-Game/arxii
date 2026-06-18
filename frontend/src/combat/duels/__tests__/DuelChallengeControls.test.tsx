/**
 * Tests for DuelChallengeControls — Task 14.
 *
 * Covers:
 * - Pending-challenge accept/decline prompt renders and dispatches correctly.
 * - Yield button visible only in an active duel (encounter_type==='duel').
 * - AcknowledgeRisk banner visible when is_lethal and no acknowledgement yet.
 * - No duel controls rendered when there is no pending challenge and no active duel.
 *
 * Note: the outgoing "challenge a co-located character" affordance (challenge button)
 * is deferred to a follow-up and is not tested here.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(),
  combatKeys: {
    all: ['combat'],
    encounter: (id: number) => ['combat', 'encounter', id],
  },
}));

import * as combatQueries from '@/combat/queries';
import {
  DuelChallengeControls,
  DuelYieldControls,
  DuelAcknowledgeRiskBanner,
} from '../DuelChallengeControls';
import type { DuelChallengeControlsProps, DuelYieldControlsProps } from '../DuelChallengeControls';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const mockedUseDispatchPlayerAction = combatQueries.useDispatchPlayerAction as ReturnType<
  typeof vi.fn
>;

const mockMutateAsync = vi.fn();

function setupMocks() {
  mockedUseDispatchPlayerAction.mockReturnValue({
    mutateAsync: mockMutateAsync,
    isPending: false,
  });
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mockMutateAsync.mockResolvedValue({ backend: 'registry', deferred: false });
});

// ---------------------------------------------------------------------------
// DuelChallengeControls — accept/decline prompt
// ---------------------------------------------------------------------------

describe('DuelChallengeControls — pending challenge prompt', () => {
  function defaultChallengeProps(
    overrides?: Partial<DuelChallengeControlsProps>
  ): DuelChallengeControlsProps {
    return {
      characterId: 10,
      hasPendingIncomingChallenge: true,
      challengerName: 'Rival Knight',
      ...overrides,
    };
  }

  it('renders accept and decline buttons when there is a pending incoming challenge', () => {
    setupMocks();

    render(<DuelChallengeControls {...defaultChallengeProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('duel-accept-btn')).toBeInTheDocument();
    expect(screen.getByTestId('duel-decline-btn')).toBeInTheDocument();
  });

  it('shows the challenger name in the prompt', () => {
    setupMocks();

    render(<DuelChallengeControls {...defaultChallengeProps({ challengerName: 'Baron Vex' })} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('duel-challenge-prompt')).toHaveTextContent('Baron Vex');
  });

  it('dispatches accept action when Accept is clicked', async () => {
    setupMocks();

    render(<DuelChallengeControls {...defaultChallengeProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-accept-btn'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: {
        backend: 'registry',
        registry_key: 'accept',
      },
      kwargs: {},
    });
  });

  it('dispatches decline action when Decline is clicked', async () => {
    setupMocks();

    render(<DuelChallengeControls {...defaultChallengeProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-decline-btn'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: {
        backend: 'registry',
        registry_key: 'decline',
      },
      kwargs: {},
    });
  });

  it('does not render the challenge prompt when there is no pending challenge', () => {
    setupMocks();

    render(
      <DuelChallengeControls
        characterId={10}
        hasPendingIncomingChallenge={false}
        challengerName={null}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('duel-challenge-prompt')).not.toBeInTheDocument();
    expect(screen.queryByTestId('duel-accept-btn')).not.toBeInTheDocument();
  });

  it('shows an error message when accept dispatch fails', async () => {
    setupMocks();
    mockMutateAsync.mockRejectedValueOnce(new Error('Challenge already expired'));

    render(<DuelChallengeControls {...defaultChallengeProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-accept-btn'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Challenge already expired');
  });

  it('buttons are disabled while a dispatch is pending', () => {
    mockedUseDispatchPlayerAction.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: true,
    });

    render(<DuelChallengeControls {...defaultChallengeProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('duel-accept-btn')).toBeDisabled();
    expect(screen.getByTestId('duel-decline-btn')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// DuelYieldControls — yield button
// ---------------------------------------------------------------------------

describe('DuelYieldControls — yield button', () => {
  function defaultYieldProps(overrides?: Partial<DuelYieldControlsProps>): DuelYieldControlsProps {
    return {
      characterId: 10,
      isActiveDuel: true,
      ...overrides,
    };
  }

  it('renders the yield button when in an active duel', () => {
    setupMocks();

    render(<DuelYieldControls {...defaultYieldProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('duel-yield-btn')).toBeInTheDocument();
  });

  it('does NOT render the yield button when not in an active duel', () => {
    setupMocks();

    render(<DuelYieldControls {...defaultYieldProps({ isActiveDuel: false })} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('duel-yield-btn')).not.toBeInTheDocument();
  });

  it('dispatches yield action when Yield is clicked', async () => {
    setupMocks();

    render(<DuelYieldControls {...defaultYieldProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-yield-btn'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: {
        backend: 'registry',
        registry_key: 'yield',
      },
      kwargs: {},
    });
  });

  it('shows a confirmation state after yield is dispatched', async () => {
    setupMocks();

    render(<DuelYieldControls {...defaultYieldProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-yield-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('duel-yield-confirmed')).toBeInTheDocument();
    });
  });

  it('shows an error when yield dispatch fails', async () => {
    setupMocks();
    mockMutateAsync.mockRejectedValueOnce(new Error('Not in a duel'));

    render(<DuelYieldControls {...defaultYieldProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-yield-btn'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Not in a duel');
  });

  it('yield button is disabled while a dispatch is pending', () => {
    mockedUseDispatchPlayerAction.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: true,
    });

    render(<DuelYieldControls {...defaultYieldProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('duel-yield-btn')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// DuelAcknowledgeRiskBanner — lethal duel risk acknowledgement
// ---------------------------------------------------------------------------

describe('DuelAcknowledgeRiskBanner', () => {
  it('renders the acknowledge button when showBanner is true', () => {
    setupMocks();

    render(<DuelAcknowledgeRiskBanner characterId={10} showBanner={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('duel-acknowledge-risk-banner')).toBeInTheDocument();
    expect(screen.getByTestId('duel-acknowledge-risk-btn')).toBeInTheDocument();
  });

  it('renders nothing when showBanner is false', () => {
    setupMocks();

    render(<DuelAcknowledgeRiskBanner characterId={10} showBanner={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('duel-acknowledge-risk-banner')).not.toBeInTheDocument();
  });

  it('dispatches acknowledge_risk when clicked', async () => {
    setupMocks();

    render(<DuelAcknowledgeRiskBanner characterId={10} showBanner={true} />, {
      wrapper: createWrapper(),
    });

    await userEvent.click(screen.getByTestId('duel-acknowledge-risk-btn'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: {
        backend: 'registry',
        registry_key: 'acknowledge_risk',
      },
      kwargs: {},
    });
  });
});
