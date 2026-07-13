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
// Mocks — mock the crossover queries (our module) and the api layer that
// @/stories/queries and @/events/queries call under the hood. This avoids
// vitest mock-path resolution issues with aliased module paths.
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

// Mock apiFetch so all React Query hooks return empty/undefined data
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
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
