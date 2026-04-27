/**
 * MyStoryOffersPage Tests
 *
 * Tests:
 *   - Pending tab shows pending offers
 *   - Decided tab shows accepted/declined/withdrawn
 *   - Empty state per tab
 *   - Loading skeleton
 *   - Accept and Decline dialogs visible on pending rows
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { MyStoryOffersPage } from '../pages/MyStoryOffersPage';
import type { PaginatedResponse, StoryGMOffer } from '../types';

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useStoryGMOffers: vi.fn(),
  useAcceptOffer: vi.fn(),
  useDeclineOffer: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeOffer(
  status: StoryGMOffer['status'],
  overrides: Partial<StoryGMOffer> = {}
): StoryGMOffer {
  return {
    id: Math.floor(Math.random() * 1000) + 1,
    story: 1,
    offered_to: 10,
    offered_by_account: 5,
    status,
    message: '',
    response_note: '',
    created_at: '2026-04-01T10:00:00Z',
    responded_at: null,
    updated_at: '2026-04-01T10:00:00Z',
    ...overrides,
  };
}

function makeOffersResponse(offers: StoryGMOffer[]): PaginatedResponse<StoryGMOffer> {
  return { count: offers.length, next: null, previous: null, results: offers };
}

function makeMutationIdle() {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle' as const,
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  };
}

function setupDefaultMocks() {
  vi.mocked(queries.useStoryGMOffers).mockReturnValue({
    data: makeOffersResponse([]),
    isLoading: false,
    isSuccess: true,
    error: null,
  } as never);
  vi.mocked(queries.useAcceptOffer).mockReturnValue(makeMutationIdle() as never);
  vi.mocked(queries.useDeclineOffer).mockReturnValue(makeMutationIdle() as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MyStoryOffersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('renders page heading', () => {
    render(<MyStoryOffersPage />, { wrapper: createWrapper() });
    expect(screen.getByText('My Story Offers')).toBeInTheDocument();
  });

  it('renders Pending and Decided tabs', () => {
    render(<MyStoryOffersPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('tab-pending')).toBeInTheDocument();
    expect(screen.getByTestId('tab-decided')).toBeInTheDocument();
  });

  it('defaults to Pending tab and shows empty state', async () => {
    render(<MyStoryOffersPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
    expect(screen.getByText('No pending offers.')).toBeInTheDocument();
  });

  it('shows pending offer row on Pending tab', async () => {
    const pendingOffer = makeOffer('pending');
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: makeOffersResponse([pendingOffer]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('offers-list')).toBeInTheDocument();
    });
    expect(screen.getByTestId('offer-row')).toBeInTheDocument();
  });

  it('shows Accept and Decline buttons on Pending tab rows', async () => {
    const pendingOffer = makeOffer('pending');
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: makeOffersResponse([pendingOffer]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('accept-offer-trigger')).toBeInTheDocument();
    });
    expect(screen.getByTestId('decline-offer-trigger')).toBeInTheDocument();
  });

  it('switches to Decided tab and shows empty state', async () => {
    const user = userEvent.setup();
    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('tab-decided'));

    await waitFor(() => {
      expect(screen.getByText('No decided offers yet.')).toBeInTheDocument();
    });
  });

  it('shows decided offer with status badge on Decided tab', async () => {
    const user = userEvent.setup();
    const acceptedOffer = makeOffer('accepted');
    // The decided tab fetches all offers (no status filter); we return the accepted one.
    vi.mocked(queries.useStoryGMOffers).mockImplementation((params) => {
      if (params?.status === 'pending') {
        return {
          data: makeOffersResponse([]),
          isLoading: false,
          isSuccess: true,
          error: null,
        } as never;
      }
      return {
        data: makeOffersResponse([acceptedOffer]),
        isLoading: false,
        isSuccess: true,
        error: null,
      } as never;
    });

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });
    await user.click(screen.getByTestId('tab-decided'));

    await waitFor(() => {
      expect(screen.getByTestId('offer-row')).toBeInTheDocument();
    });
    expect(screen.getByTestId('offer-status-badge')).toHaveTextContent('Accepted');
  });

  it('shows loading skeleton during pending state', () => {
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('offers-skeleton')).toBeInTheDocument();
  });
});

describe('AcceptOfferDialog interaction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('opens AcceptOfferDialog when Accept is clicked', async () => {
    const user = userEvent.setup();
    const pendingOffer = makeOffer('pending');
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: makeOffersResponse([pendingOffer]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('accept-offer-trigger')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('accept-offer-trigger'));

    expect(screen.getByText('Accept story offer')).toBeInTheDocument();
  });

  it('AcceptOfferDialog submits with correct offerId', async () => {
    const user = userEvent.setup();
    const acceptMutate = vi.fn();
    vi.mocked(queries.useAcceptOffer).mockReturnValue({
      ...makeMutationIdle(),
      mutate: acceptMutate,
    } as never);

    const pendingOffer = makeOffer('pending', { id: 42 });
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: makeOffersResponse([pendingOffer]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('accept-offer-trigger')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('accept-offer-trigger'));

    await user.click(screen.getByTestId('accept-confirm-button'));

    expect(acceptMutate).toHaveBeenCalledWith(
      expect.objectContaining({ offerId: 42 }),
      expect.any(Object)
    );
  });
});

describe('DeclineOfferDialog interaction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('opens DeclineOfferDialog when Decline is clicked', async () => {
    const user = userEvent.setup();
    const pendingOffer = makeOffer('pending');
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: makeOffersResponse([pendingOffer]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('decline-offer-trigger')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('decline-offer-trigger'));

    expect(screen.getByText('Decline story offer')).toBeInTheDocument();
  });

  it('DeclineOfferDialog submits with correct offerId', async () => {
    const user = userEvent.setup();
    const declineMutate = vi.fn();
    vi.mocked(queries.useDeclineOffer).mockReturnValue({
      ...makeMutationIdle(),
      mutate: declineMutate,
    } as never);

    const pendingOffer = makeOffer('pending', { id: 77 });
    vi.mocked(queries.useStoryGMOffers).mockReturnValue({
      data: makeOffersResponse([pendingOffer]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    render(<MyStoryOffersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('decline-offer-trigger')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('decline-offer-trigger'));

    await user.click(screen.getByTestId('decline-confirm-button'));

    expect(declineMutate).toHaveBeenCalledWith(
      expect.objectContaining({ offerId: 77 }),
      expect.any(Object)
    );
  });
});
