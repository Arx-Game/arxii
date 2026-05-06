/**
 * SoulTetherRescuePrompt tests
 *
 * Covers:
 * 1. Renders nothing when there are no pending stage-advance offers.
 * 2. Renders the prompt with sinner name, corruption stage, costs, and commit_units_max.
 * 3. Clicking Confirm fires useRespondToStageAdvance with accept (units_committed = commit_units_max).
 * 4. Clicking Decline fires useRespondToStageAdvance with units_committed = 0.
 * 5. Both buttons are disabled while the mutation is pending.
 * 6. Expired offers (expires_at < now) are filtered client-side and don't render.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { SoulTetherRescuePrompt } from '../components/SoulTetherRescuePrompt';
import type { useRespondToStageAdvance } from '../queries';
import type { PendingStageAdvanceOffer } from '../types';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  usePendingStageAdvanceOffers: vi.fn(),
  useRespondToStageAdvance: vi.fn(),
  magicKeys: {
    stageAdvancePending: () => ['magic', 'soul-tether', 'stage-advance', 'pending'],
  },
}));

// ---------------------------------------------------------------------------
// Shared auth state — defined before vi.mock factories run
// ---------------------------------------------------------------------------

const defaultAuthState = {
  auth: {
    account: {
      id: 1,
      username: 'testuser',
      available_characters: [
        {
          id: 55,
          name: 'Sineater Character',
          currently_puppeted_in_session: true,
        },
      ],
    },
  },
};

vi.mock('react-redux', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-redux')>();
  return {
    ...actual,
    useSelector: vi.fn((selector: (state: unknown) => unknown) => selector(defaultAuthState)),
  };
});

import * as magicQueries from '../queries';

// Helper type to check return types
import type { useRespondToStageAdvance } from '../queries';

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

const FUTURE_ISO = new Date(Date.now() + 60_000).toISOString();
const PAST_ISO = new Date(Date.now() - 1_000).toISOString();

function makeOffer(overrides: Partial<PendingStageAdvanceOffer> = {}): PendingStageAdvanceOffer {
  return {
    id: 1,
    sinner_sheet_id: 10,
    sinner_persona_name: 'Alaric',
    scene_id: 5,
    scene_name: 'The Shadowed Hall',
    resonance_id: 3,
    sinner_corruption_stage: 2,
    commit_units_max: 4,
    strain_cost_per_unit: 1,
    created_at: new Date(Date.now() - 5_000).toISOString(),
    expires_at: FUTURE_ISO,
    ...overrides,
  };
}

const mockMutate = vi.fn();

function setupMocks(options?: { offers?: PendingStageAdvanceOffer[]; isPending?: boolean }) {
  const offers = options?.offers ?? [];
  const isPending = options?.isPending ?? false;

  // The component now uses usePendingStageAdvanceOffers hook.
  vi.mocked(magicQueries.usePendingStageAdvanceOffers).mockReturnValue({
    data: {
      count: offers.length,
      next: null,
      previous: null,
      results: offers,
    },
    isLoading: false,
    isError: false,
    isPending: false,
  } as unknown as ReturnType<typeof magicQueries.usePendingStageAdvanceOffers>);

  // useRespondToStageAdvance is called from the queries module (mocked).
  vi.mocked(magicQueries.useRespondToStageAdvance).mockReturnValue({
    mutate: mockMutate,
    isPending,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useRespondToStageAdvance>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SoulTetherRescuePrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // 1. Renders nothing when there are no pending offers.
  it('renders nothing when there are no pending stage-advance offers', () => {
    setupMocks({ offers: [] });

    const { container } = render(<SoulTetherRescuePrompt />, {
      wrapper: createWrapper(),
    });

    // After data loads, still nothing (no offers).
    expect(container.firstChild).toBeNull();
  });

  // 2. Renders the prompt with sinner name, corruption stage, costs, and commit_units_max.
  it('renders offer details when a pending stage-advance offer is present', async () => {
    const offer = makeOffer();
    setupMocks({ offers: [offer] });

    render(<SoulTetherRescuePrompt />, { wrapper: createWrapper() });

    // Sinner name
    await waitFor(() => expect(screen.getByText(/Alaric/)).toBeInTheDocument());
    // Stage
    expect(screen.getByText(/stage 2/i)).toBeInTheDocument();
    // Cost per unit
    expect(screen.getByText(/1 strain per unit/i)).toBeInTheDocument();
    // Max units
    expect(screen.getByText(/4/)).toBeInTheDocument();
    // Confirm + Decline buttons
    expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /decline/i })).toBeInTheDocument();
  });

  // 3. Clicking Confirm fires mutation with units_committed = commit_units_max.
  it('clicking Confirm fires useRespondToStageAdvance with units_committed = commit_units_max', async () => {
    const offer = makeOffer({ commit_units_max: 3 });
    setupMocks({ offers: [offer] });

    render(<SoulTetherRescuePrompt />, { wrapper: createWrapper() });

    const confirmBtn = await screen.findByRole('button', { name: /confirm/i });
    fireEvent.click(confirmBtn);

    expect(mockMutate).toHaveBeenCalledWith({
      sinner_sheet_id: 10,
      sineater_sheet_id: 55,
      units_committed: 3,
    });
  });

  // 4. Clicking Decline fires mutation with units_committed = 0.
  it('clicking Decline fires useRespondToStageAdvance with units_committed = 0', async () => {
    const offer = makeOffer();
    setupMocks({ offers: [offer] });

    render(<SoulTetherRescuePrompt />, { wrapper: createWrapper() });

    const declineBtn = await screen.findByRole('button', { name: /decline/i });
    fireEvent.click(declineBtn);

    expect(mockMutate).toHaveBeenCalledWith({
      sinner_sheet_id: 10,
      sineater_sheet_id: 55,
      units_committed: 0,
    });
  });

  // 5. Both buttons are disabled while the mutation is pending.
  it('disables both buttons while the mutation is pending', async () => {
    const offer = makeOffer();
    setupMocks({ offers: [offer], isPending: true });

    render(<SoulTetherRescuePrompt />, { wrapper: createWrapper() });

    const confirmBtn = await screen.findByRole('button', { name: /confirm/i });
    const declineBtn = screen.getByRole('button', { name: /decline/i });
    expect(confirmBtn).toBeDisabled();
    expect(declineBtn).toBeDisabled();
  });

  // 6. Expired offers are filtered client-side and don't render.
  it('filters out expired offers (expires_at < now) and renders nothing', () => {
    const expiredOffer = makeOffer({ expires_at: PAST_ISO });
    setupMocks({ offers: [expiredOffer] });

    const { container } = render(<SoulTetherRescuePrompt />, {
      wrapper: createWrapper(),
    });

    // Expired offer is filtered; nothing renders.
    expect(container.firstChild).toBeNull();
  });

  // Bonus: non-expired offers render when mixed with expired.
  it('renders only non-expired offers when mixed with expired ones', async () => {
    const activeOffer = makeOffer({ id: 1, sinner_persona_name: 'Alaric', expires_at: FUTURE_ISO });
    const expiredOffer = makeOffer({ id: 2, sinner_persona_name: 'Veyra', expires_at: PAST_ISO });
    setupMocks({ offers: [activeOffer, expiredOffer] });

    render(<SoulTetherRescuePrompt />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText(/Alaric/)).toBeInTheDocument());
    expect(screen.queryByText(/Veyra/)).not.toBeInTheDocument();
  });
});
