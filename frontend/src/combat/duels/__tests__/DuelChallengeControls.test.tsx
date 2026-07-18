/**
 * Tests for DuelYieldControls / DuelAcknowledgeRiskBanner — Task 14 (#2423 follow-up).
 *
 * Covers:
 * - Yield button visible only in an active duel (encounter_type==='duel').
 * - AcknowledgeRisk banner visible when is_lethal and no acknowledgement yet.
 * - Both honor the dispatch contract: a resolved `{success: false}` result must
 *   NOT flip confirmed/acknowledged state and must surface the server message (#2423).
 *
 * Note: the outgoing "challenge a co-located character" affordance (challenge button)
 * is deferred to a follow-up and is not tested here. The former Accept/Decline prompt
 * (DuelChallengeControls) was deleted (#2423) — that UI now lives in DuelChallengeNotifier.
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
import { DuelYieldControls, DuelAcknowledgeRiskBanner } from '../DuelChallengeControls';
import type { DuelYieldControlsProps } from '../DuelChallengeControls';

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

  it('does not show the confirmed state when the dispatch resolves success:false (#2423)', async () => {
    setupMocks();
    mockMutateAsync.mockResolvedValueOnce({ success: false, message: 'Not your turn.' });

    render(<DuelYieldControls {...defaultYieldProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('duel-yield-btn'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Not your turn.');
    expect(screen.queryByTestId('duel-yield-confirmed')).not.toBeInTheDocument();
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

  it('keeps the banner visible when the dispatch resolves success:false (#2423)', async () => {
    setupMocks();
    mockMutateAsync.mockResolvedValueOnce({ success: false, message: 'Not your turn.' });

    render(<DuelAcknowledgeRiskBanner characterId={10} showBanner={true} />, {
      wrapper: createWrapper(),
    });

    await userEvent.click(screen.getByTestId('duel-acknowledge-risk-btn'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Not your turn.');
    expect(screen.getByTestId('duel-acknowledge-risk-banner')).toBeInTheDocument();
  });
});
