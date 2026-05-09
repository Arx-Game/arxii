import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ThreadWeavingTeachingOffer, PaginatedTeachingOfferList } from '../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useTeachingOffers: vi.fn(),
  useAcceptTeachingOffer: vi.fn(),
}));

import * as magicQueries from '@/magic/queries';
import { WeavingTeachingOffersPage } from '../WeavingTeachingOffersPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const makeOffer = (
  overrides: Partial<ThreadWeavingTeachingOffer> = {}
): ThreadWeavingTeachingOffer => ({
  id: 1,
  teacher: 42,
  unlock: 10,
  unlock_target_kind: 'TRAIT',
  unlock_display_name: 'Persuasion',
  unlock_xp_cost: 8,
  effective_xp_cost_for_viewer: 8,
  pitch: 'I can teach you the art of persuasion.',
  gold_cost: 250,
  ...overrides,
});

type UseQueryReturn<T> = {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: null;
};

function makeQueryResult<T>(data: T | undefined, loading = false): UseQueryReturn<T> {
  return { data, isLoading: loading, isError: false, error: null };
}

function makeListResult(
  offers: ThreadWeavingTeachingOffer[],
  loading = false
): UseQueryReturn<PaginatedTeachingOfferList> {
  return makeQueryResult(
    { count: offers.length, next: null, previous: null, results: offers },
    loading
  );
}

const mockMutate = vi.fn();

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockMutate.mockReset();

  vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
    makeListResult([]) as ReturnType<typeof magicQueries.useTeachingOffers>
  );

  vi.mocked(magicQueries.useAcceptTeachingOffer).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
  } as unknown as ReturnType<typeof magicQueries.useAcceptTeachingOffer>);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WeavingTeachingOffersPage', () => {
  it('renders the page heading', () => {
    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });
    expect(
      screen.getByRole('heading', { name: 'Thread Weaving Teaching Offers' })
    ).toBeInTheDocument();
  });

  it('shows empty state when no offers', () => {
    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('teaching-offers-empty')).toBeInTheDocument();
    expect(screen.getByText('No teaching offers available right now.')).toBeInTheDocument();
  });

  it('renders offer list with cost when offers are present', () => {
    const offer = makeOffer({
      id: 1,
      teacher: 42,
      unlock_target_kind: 'TRAIT',
      unlock_display_name: 'Persuasion',
      effective_xp_cost_for_viewer: 8,
      gold_cost: 250,
    });

    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult([offer]) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });

    expect(screen.getByTestId('teaching-offers-list')).toBeInTheDocument();
    expect(screen.getByTestId('teaching-offer-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('teaching-offer-teacher')).toHaveTextContent('Teacher #42');
    expect(screen.getByTestId('teaching-offer-unlock')).toHaveTextContent('TRAIT');
    expect(screen.getByTestId('teaching-offer-unlock')).toHaveTextContent('Persuasion');
    expect(screen.getByTestId('teaching-offer-xp-cost')).toHaveTextContent('8 XP');
    expect(screen.getByTestId('teaching-offer-gold-cost')).toHaveTextContent('250');
  });

  it('renders pitch text when offer has pitch', () => {
    const offer = makeOffer({ pitch: 'I can teach you the art of persuasion.' });

    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult([offer]) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('teaching-offer-pitch')).toHaveTextContent(
      'I can teach you the art of persuasion.'
    );
  });

  it('shows loading skeleton while fetching', () => {
    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult([], true) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('teaching-offers-loading')).toBeInTheDocument();
  });

  it('disables accept button when effective_xp_cost_for_viewer is null (alt-ambiguous)', () => {
    const offer = makeOffer({ effective_xp_cost_for_viewer: null });

    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult([offer]) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });

    const acceptBtn = screen.getByTestId('teaching-offer-accept-btn-1');
    expect(acceptBtn).toBeDisabled();
    expect(screen.getByTestId('teaching-offer-xp-cost')).toHaveTextContent(
      'Select character to see XP cost'
    );
  });

  it('opens AcceptOfferDialog when Accept Offer button is clicked', () => {
    const offer = makeOffer({ id: 7, effective_xp_cost_for_viewer: 12 });

    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult([offer]) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });

    // Dialog should not be visible initially
    expect(screen.queryByTestId('accept-offer-dialog')).not.toBeInTheDocument();

    // Click the accept button
    fireEvent.click(screen.getByTestId('teaching-offer-accept-btn-7'));

    // Dialog should now be visible
    expect(screen.getByTestId('accept-offer-dialog')).toBeInTheDocument();
  });

  it('fires the accept mutation when dialog confirm is clicked', () => {
    const offer = makeOffer({ id: 5, effective_xp_cost_for_viewer: 24 });

    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult([offer]) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });

    // Open dialog
    fireEvent.click(screen.getByTestId('teaching-offer-accept-btn-5'));
    expect(screen.getByTestId('accept-offer-dialog')).toBeInTheDocument();

    // Click confirm
    fireEvent.click(screen.getByTestId('accept-offer-confirm'));

    expect(mockMutate).toHaveBeenCalledWith(
      { offerId: 5 },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it('renders multiple offers', () => {
    const offers = [
      makeOffer({ id: 1, unlock_display_name: 'Persuasion', teacher: 10 }),
      makeOffer({
        id: 2,
        unlock_display_name: 'Deception',
        teacher: 20,
        unlock_target_kind: 'TECHNIQUE',
      }),
    ];

    vi.mocked(magicQueries.useTeachingOffers).mockReturnValue(
      makeListResult(offers) as ReturnType<typeof magicQueries.useTeachingOffers>
    );

    render(<WeavingTeachingOffersPage />, { wrapper: createWrapper() });

    expect(screen.getByTestId('teaching-offer-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('teaching-offer-card-2')).toBeInTheDocument();
  });
});
