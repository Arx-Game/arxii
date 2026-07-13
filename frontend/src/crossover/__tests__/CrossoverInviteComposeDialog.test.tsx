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

vi.mock('@/stories/queries', () => ({
  useStoryList: vi.fn(() => ({
    data: {
      count: 2,
      next: null,
      previous: null,
      results: [
        { id: 10, title: 'Story Alpha' },
        { id: 20, title: 'Story Beta' },
      ],
    },
    isLoading: false,
  })),
  useEpisodeList: vi.fn(() => ({
    data: {
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 30, name: 'Episode 1', order: 1 }],
    },
    isLoading: false,
  })),
}));

vi.mock('@/events/queries', () => ({
  fetchEvents: vi.fn(),
}));

// No need to mock @tanstack/react-query globally — the dialog's useQuery
// for events will just return undefined data when fetchEvents is mocked
// and there's no query client. We provide a query client in renderDialog.

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
