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
  crossoverKeys: { all: ['crossover'] },
}));

vi.mock('@/stories/queries', () => ({
  useStoryList: () => ({
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
  }),
  useEpisodeList: () => ({
    data: {
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 30, name: 'Episode 1', order: 1 }],
    },
    isLoading: false,
  }),
}));

vi.mock('@/events/queries', () => ({
  fetchEvents: vi.fn(),
}));

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQuery: () => ({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [
          { id: 1, name: 'Event One', scheduled_real_time: '2026-08-01T00:00:00Z' },
          { id: 2, name: 'Event Two', scheduled_real_time: null },
        ],
      },
    }),
  };
});

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
