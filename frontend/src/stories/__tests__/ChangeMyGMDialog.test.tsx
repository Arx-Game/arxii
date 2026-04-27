/**
 * ChangeMyGMDialog Tests
 *
 * Tests for the combined withdraw + offer-to-GM dialog:
 *   - Button label adapts to story.primary_table presence
 *   - Withdraw step renders and submits
 *   - Offer step renders with GM picker and message
 *   - Offer step submits with correct payload
 *   - Toast on success
 *   - Validation error surfaces inline
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { ChangeMyGMDialog } from '../components/ChangeMyGMDialog';
import type { Story, GMProfile, PaginatedResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useDetachStoryFromTable: vi.fn(),
  useOfferStoryToGM: vi.fn(),
  useGMProfiles: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

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

const makeStory = (overrides: Partial<Story> = {}): Story => ({
  id: 1,
  title: 'A Knights Tale',
  description: '',
  scope: 'character',
  status: 'active',
  privacy: 'private',
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 42,
  chapters_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  completed_at: null,
  primary_table: null,
  ...overrides,
});

const makeGMProfile = (overrides: Partial<GMProfile> = {}): GMProfile => ({
  id: 10,
  account: 100,
  account_username: 'gm_alice',
  level: 'gm',
  approved_at: '2025-01-01T00:00:00Z',
  ...overrides,
});

function makeGMProfilesResponse(profiles: GMProfile[]): PaginatedResponse<GMProfile> {
  return { count: profiles.length, next: null, previous: null, results: profiles };
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
  vi.mocked(queries.useDetachStoryFromTable).mockReturnValue(makeMutationIdle() as never);
  vi.mocked(queries.useOfferStoryToGM).mockReturnValue(makeMutationIdle() as never);
  vi.mocked(queries.useGMProfiles).mockReturnValue({
    data: makeGMProfilesResponse([]),
    isLoading: false,
    isSuccess: true,
    error: null,
  } as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ChangeMyGMDialog — button label', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('shows "Change my GM" when story has a primary_table', () => {
    const story = makeStory({ primary_table: 5 });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('change-gm-button')).toHaveTextContent('Change my GM');
  });

  it('shows "Offer to a GM" when story has primary_table=null', () => {
    const story = makeStory({ primary_table: null });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('change-gm-button')).toHaveTextContent('Offer to a GM');
  });
});

describe('ChangeMyGMDialog — withdraw step', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('opens to withdraw step when story has primary_table', async () => {
    const user = userEvent.setup();
    const story = makeStory({ primary_table: 5 });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));

    expect(screen.getByText('Withdraw from current GM?')).toBeInTheDocument();
  });

  it('calls detachStoryFromTable when Withdraw is clicked', async () => {
    const user = userEvent.setup();
    const mutateFn = vi.fn();
    vi.mocked(queries.useDetachStoryFromTable).mockReturnValue({
      ...makeMutationIdle(),
      mutate: mutateFn,
    } as never);

    const story = makeStory({ primary_table: 5 });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));
    await user.click(screen.getByRole('button', { name: /withdraw/i }));

    expect(mutateFn).toHaveBeenCalledWith(story.id, expect.any(Object));
  });
});

describe('ChangeMyGMDialog — offer step', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('opens directly to offer step when story has no primary_table', async () => {
    const user = userEvent.setup();
    const story = makeStory({ primary_table: null });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));

    // The dialog title "Offer to a GM" renders inside the dialog — button also has
    // same text, so use getByRole(heading) to disambiguate.
    expect(screen.getByRole('heading', { name: /offer to a gm/i })).toBeInTheDocument();
    expect(screen.getByTestId('gm-search-input')).toBeInTheDocument();
  });

  it('shows GM options when search has 2+ chars', async () => {
    const user = userEvent.setup();
    const gmProfile = makeGMProfile();
    vi.mocked(queries.useGMProfiles).mockReturnValue({
      data: makeGMProfilesResponse([gmProfile]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    const story = makeStory({ primary_table: null });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));

    const input = screen.getByTestId('gm-search-input');
    await user.type(input, 'gm');

    await waitFor(() => {
      expect(screen.getByTestId('gm-option-10')).toBeInTheDocument();
    });
  });

  it('submit button is disabled until GM is selected', async () => {
    const user = userEvent.setup();
    const story = makeStory({ primary_table: null });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));

    expect(screen.getByTestId('offer-submit-button')).toBeDisabled();
  });

  it('calls offerStoryToGM with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateFn = vi.fn();
    vi.mocked(queries.useOfferStoryToGM).mockReturnValue({
      ...makeMutationIdle(),
      mutate: mutateFn,
    } as never);

    const gmProfile = makeGMProfile();
    vi.mocked(queries.useGMProfiles).mockReturnValue({
      data: makeGMProfilesResponse([gmProfile]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    const story = makeStory({ primary_table: null });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));

    // Type in GM search
    const input = screen.getByTestId('gm-search-input');
    await user.type(input, 'gm');

    // Wait for dropdown and select GM
    await waitFor(() => {
      expect(screen.getByTestId('gm-option-10')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('gm-option-10'));

    // Verify GM is selected
    await waitFor(() => {
      expect(screen.getByTestId('gm-selected-confirmation')).toBeInTheDocument();
    });

    // Add a message
    await user.type(screen.getByTestId('offer-message-input'), 'Great story for you!');

    // Submit
    fireEvent.submit(screen.getByTestId('offer-submit-button').closest('form')!);

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({
        storyId: 1,
        gm_profile_id: 10,
        message: 'Great story for you!',
      }),
      expect.any(Object)
    );
  });

  it('shows toast success after offer is sent', async () => {
    const user = userEvent.setup();
    const mutateFn = vi.fn((_vars, { onSuccess }: { onSuccess: () => void }) => onSuccess());
    vi.mocked(queries.useOfferStoryToGM).mockReturnValue({
      ...makeMutationIdle(),
      mutate: mutateFn,
    } as never);

    const gmProfile = makeGMProfile();
    vi.mocked(queries.useGMProfiles).mockReturnValue({
      data: makeGMProfilesResponse([gmProfile]),
      isLoading: false,
      isSuccess: true,
      error: null,
    } as never);

    const story = makeStory({ primary_table: null });
    render(<ChangeMyGMDialog story={story} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('change-gm-button'));

    const input = screen.getByTestId('gm-search-input');
    await user.type(input, 'gm');
    await waitFor(() => {
      expect(screen.getByTestId('gm-option-10')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('gm-option-10'));

    await waitFor(() => {
      expect(screen.getByTestId('gm-selected-confirmation')).toBeInTheDocument();
    });

    fireEvent.submit(screen.getByTestId('offer-submit-button').closest('form')!);

    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(expect.stringContaining('gm_alice'));
  });
});
