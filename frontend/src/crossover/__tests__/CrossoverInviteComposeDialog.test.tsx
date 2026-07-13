/**
 * CrossoverInviteComposeDialog tests (#2075).
 *
 * Tests: dialog opens, submit button disabled until required fields selected.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { CrossoverInviteComposeDialog } from '../components/CrossoverInviteComposeDialog';

// ---------------------------------------------------------------------------
// Mocks
//
// The compose dialog imports from three query modules:
// - ../queries (crossover) — our module
// - @/stories/queries — stories hooks
// - @/events/queries — events fetch
//
// We mock all three. The crossover queries mock must export everything the
// dialog (and its child components) import. The stories/events mocks provide
// empty data so the pickers render with no options.
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useAcceptCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useDeclineCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useWithdrawCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useCrossoverInvites: () => ({ data: undefined, isLoading: false }),
  useEpisodeScenesForScene: () => ({ data: undefined, isLoading: false }),
  getStakesSummary: vi.fn(),
  crossoverKeys: { all: ['crossover'] },
}));

// Mock the stories/queries module with the hooks the dialog imports.
// Using vi.mock with the alias path — vitest resolves this via the vite alias.
vi.mock('@/stories/queries', () => ({
  useStoryList: () => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  }),
  useEpisodeList: () => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  }),
}));

vi.mock('@/events/queries', () => ({
  fetchEvents: vi.fn().mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  }),
}));

function renderDialog(props?: { currentStoryId?: number }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CrossoverInviteComposeDialog currentStoryId={props?.currentStoryId} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CrossoverInviteComposeDialog', () => {
  it('renders the trigger button', () => {
    renderDialog();
    expect(screen.getByTestId('crossover-invite-button')).toBeTruthy();
  });

  it('opens the dialog when trigger is clicked', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId('crossover-invite-button'));
    expect(screen.getByText('Send Crossover Invite')).toBeTruthy();
  });

  it('disables submit until event and story are selected', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId('crossover-invite-button'));
    const submit = screen.getByTestId('crossover-submit-button');
    expect(submit.hasAttribute('disabled')).toBe(true);
  });
});
