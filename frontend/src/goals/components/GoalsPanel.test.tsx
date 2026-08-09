/**
 * GoalsPanel tests (#3045). Mocks the active-character resolution chain
 * (mirrors GMAdjudicationPanel.test.tsx) and `../queries` (no msw).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { GoalsPanel } from './GoalsPanel';
import type {
  useCreateGoalJournalMutation,
  useGoalDomainsQuery,
  useMyGoalsQuery,
} from '../queries';

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [{ id: 1, name: 'GoalChar', character_id: 42 }],
  })),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'GoalChar' }, auth: {} })
  ),
}));

vi.mock('../queries', () => ({
  useMyGoalsQuery: vi.fn(),
  useGoalDomainsQuery: vi.fn(),
  useCreateGoalJournalMutation: vi.fn(),
}));

import * as goalsQueries from '../queries';

const goal = { id: 1, domain: 5, domain_name: 'Wealth', points: 10, notes: '', updated_at: '' };

function setupMocks(options?: {
  goals?: (typeof goal)[];
  pointsRemaining?: number;
  isLoading?: boolean;
}) {
  const logMutate = vi.fn();

  vi.mocked(goalsQueries.useMyGoalsQuery).mockReturnValue({
    data: {
      goals: options?.goals ?? [goal],
      total_points: 10,
      points_remaining: options?.pointsRemaining ?? 15,
      revision: { last_revised_at: null, can_revise: true },
    },
    isLoading: options?.isLoading ?? false,
    error: null,
  } as unknown as ReturnType<typeof useMyGoalsQuery>);

  vi.mocked(goalsQueries.useGoalDomainsQuery).mockReturnValue({
    data: [{ id: 5, name: 'Wealth', description: '', display_order: 1, is_optional: false }],
  } as unknown as ReturnType<typeof useGoalDomainsQuery>);

  vi.mocked(goalsQueries.useCreateGoalJournalMutation).mockReturnValue({
    mutate: logMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateGoalJournalMutation>);

  return { logMutate };
}

describe('GoalsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('resolves the goals query against the active character id', () => {
    setupMocks();
    renderWithProviders(<GoalsPanel />);
    expect(goalsQueries.useMyGoalsQuery).toHaveBeenCalledWith(42);
  });

  it('renders current goal allocations', () => {
    setupMocks();
    renderWithProviders(<GoalsPanel />);
    expect(screen.getByText('Wealth')).toBeInTheDocument();
    expect(screen.getByText('10 pts')).toBeInTheDocument();
    expect(screen.getByText('15 points remaining')).toBeInTheDocument();
  });

  it('shows the empty state when no goals are set', () => {
    setupMocks({ goals: [] });
    renderWithProviders(<GoalsPanel />);
    expect(screen.getByTestId('goals-empty')).toBeInTheDocument();
  });

  it('submitting the log-progress dialog dispatches the create mutation', async () => {
    const { logMutate } = setupMocks();
    renderWithProviders(<GoalsPanel />);

    await userEvent.click(screen.getByTestId('goals-log-progress-trigger'));
    await userEvent.type(screen.getByTestId('goals-log-title-input'), 'A step forward');
    await userEvent.type(screen.getByTestId('goals-log-content-input'), 'Today I made progress.');
    await userEvent.click(screen.getByTestId('goals-log-submit'));

    expect(logMutate).toHaveBeenCalledWith(
      {
        domain: null,
        title: 'A step forward',
        content: 'Today I made progress.',
        is_public: false,
      },
      expect.anything()
    );
  });

  it('disables submit until both title and content are filled in', async () => {
    setupMocks();
    renderWithProviders(<GoalsPanel />);

    await userEvent.click(screen.getByTestId('goals-log-progress-trigger'));
    expect(screen.getByTestId('goals-log-submit')).toBeDisabled();

    await userEvent.type(screen.getByTestId('goals-log-title-input'), 'Title only');
    expect(screen.getByTestId('goals-log-submit')).toBeDisabled();
  });
});
