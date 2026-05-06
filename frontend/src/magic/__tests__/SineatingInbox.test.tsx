/**
 * SineatingInbox tests
 *
 * Covers: empty state, renders one row per offer, shows offer fields,
 * Accept/Decline mutations fire with correct payload, buttons disable
 * while mutation is pending.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { SineatingInbox } from '../components/SineatingInbox';
import * as queries from '@/magic/queries';
import type { SineatingPendingOffer } from '@/magic/types';

// ---------------------------------------------------------------------------
// Mock @/magic/queries
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries');

// ---------------------------------------------------------------------------
// Mock react-redux useSelector — provide a puppeted character with sheet id 7
// ---------------------------------------------------------------------------

const defaultAuthState = {
  auth: {
    account: {
      id: 1,
      username: 'sineater_user',
      available_characters: [
        {
          id: 7,
          name: 'Lyra',
          character_type: 'PC',
          roster_status: 'active',
          personas: [],
          last_location: null,
          portrait_url: null,
          currently_puppeted_in_session: true,
        },
      ],
      pending_applications: [],
    },
  },
};

let currentAuthState = defaultAuthState;

vi.mock('react-redux', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-redux')>();
  return {
    ...actual,
    useSelector: vi.fn((selector: (state: unknown) => unknown) => selector(currentAuthState)),
  };
});

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

const mockMutate = vi.fn();

function makeMutationIdle() {
  return {
    mutate: mockMutate,
    isPending: false,
    isSuccess: false,
    isIdle: true,
    isError: false,
    error: null,
    data: undefined,
    status: 'idle' as const,
  } as unknown as ReturnType<typeof queries.useRespondToSineating>;
}

function makeMutationPending() {
  return {
    mutate: mockMutate,
    isPending: true,
    isSuccess: false,
    isIdle: false,
    isError: false,
    error: null,
    data: undefined,
    status: 'pending' as const,
  } as unknown as ReturnType<typeof queries.useRespondToSineating>;
}

function makeOfferQueryResult(offers: SineatingPendingOffer[]) {
  return {
    data: { count: offers.length, next: null, previous: null, results: offers },
    isLoading: false,
    isError: false,
    isPending: false,
  } as unknown as ReturnType<typeof queries.usePendingSineatingOffers>;
}

function makeEmptyQueryResult() {
  return {
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
    isError: false,
    isPending: false,
  } as unknown as ReturnType<typeof queries.usePendingSineatingOffers>;
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const offer1: SineatingPendingOffer = {
  id: 101,
  sinner_sheet_id: 42,
  sinner_persona_name: 'Marek the Hollow',
  scene_id: 5,
  scene_name: 'The Darkened Hall',
  resonance_id: 3,
  units_offered: 4,
  anima_cost_per_unit: 2,
  fatigue_cost_per_unit: 1,
  created_at: '2026-05-06T10:00:00Z',
};

const offer2: SineatingPendingOffer = {
  id: 102,
  sinner_sheet_id: 55,
  sinner_persona_name: 'Elara Voss',
  scene_id: 6,
  scene_name: 'The Mire',
  resonance_id: 4,
  units_offered: 2,
  anima_cost_per_unit: 3,
  fatigue_cost_per_unit: 2,
  created_at: '2026-05-06T11:00:00Z',
};

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SineatingInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentAuthState = defaultAuthState;
    vi.mocked(queries.useRespondToSineating).mockReturnValue(makeMutationIdle());
  });

  // 1. Renders nothing when there are no pending offers
  it('renders nothing when there are no pending offers', () => {
    vi.mocked(queries.usePendingSineatingOffers).mockReturnValue(makeEmptyQueryResult());

    const Wrapper = createWrapper();
    const { container } = render(
      <Wrapper>
        <SineatingInbox />
      </Wrapper>
    );

    expect(container.firstChild).toBeNull();
  });

  // 2. Renders one row per offer
  it('renders one row per offer', () => {
    vi.mocked(queries.usePendingSineatingOffers).mockReturnValue(
      makeOfferQueryResult([offer1, offer2])
    );

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <SineatingInbox />
      </Wrapper>
    );

    expect(screen.getByText(/Marek the Hollow/)).toBeInTheDocument();
    expect(screen.getByText(/Elara Voss/)).toBeInTheDocument();
  });

  // 3. Each row shows sinner_persona_name, units_offered, anima_cost_per_unit, fatigue_cost_per_unit
  it('shows sinner name, units offered, and costs per unit', () => {
    vi.mocked(queries.usePendingSineatingOffers).mockReturnValue(makeOfferQueryResult([offer1]));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <SineatingInbox />
      </Wrapper>
    );

    expect(screen.getByText(/Marek the Hollow/)).toBeInTheDocument();
    expect(screen.getByText(/4 units/)).toBeInTheDocument();
    expect(screen.getByText(/2 anima/)).toBeInTheDocument();
    expect(screen.getByText(/1 fatigue/)).toBeInTheDocument();
  });

  // 4. Clicking Accept fires mutation with { sinner_sheet_id, sineater_sheet_id, units_accepted: units_offered }
  it('fires mutation with units_accepted = units_offered when Accept is clicked', async () => {
    vi.mocked(queries.usePendingSineatingOffers).mockReturnValue(makeOfferQueryResult([offer1]));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <SineatingInbox />
      </Wrapper>
    );

    const acceptButton = screen.getByRole('button', { name: /accept/i });
    await userEvent.click(acceptButton);

    expect(mockMutate).toHaveBeenCalledWith({
      sinner_sheet_id: offer1.sinner_sheet_id,
      sineater_sheet_id: 7,
      units_accepted: offer1.units_offered,
    });
  });

  // 5. Clicking Decline fires mutation with units_accepted = 0
  it('fires mutation with units_accepted = 0 when Decline is clicked', async () => {
    vi.mocked(queries.usePendingSineatingOffers).mockReturnValue(makeOfferQueryResult([offer1]));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <SineatingInbox />
      </Wrapper>
    );

    const declineButton = screen.getByRole('button', { name: /decline/i });
    await userEvent.click(declineButton);

    expect(mockMutate).toHaveBeenCalledWith({
      sinner_sheet_id: offer1.sinner_sheet_id,
      sineater_sheet_id: 7,
      units_accepted: 0,
    });
  });

  // 6. While mutation is pending, buttons are disabled
  it('disables Accept and Decline buttons while mutation is pending', () => {
    vi.mocked(queries.usePendingSineatingOffers).mockReturnValue(makeOfferQueryResult([offer1]));
    vi.mocked(queries.useRespondToSineating).mockReturnValue(makeMutationPending());

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <SineatingInbox />
      </Wrapper>
    );

    expect(screen.getByRole('button', { name: /accept/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /decline/i })).toBeDisabled();
  });
});
