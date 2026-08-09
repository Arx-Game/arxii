/**
 * ClassUnlocksCard tests (#3045). Mocks `@/progression/queries` (no msw).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ClassUnlocksCard } from './ClassUnlocksCard';
import type { useProgressionUnlocksQuery, usePurchaseUnlockMutation } from '@/progression/queries';

vi.mock('@/progression/queries', () => ({
  useProgressionUnlocksQuery: vi.fn(),
  usePurchaseUnlockMutation: vi.fn(),
}));

import * as progressionQueries from '@/progression/queries';

const item = {
  unlock_type: 'class_level',
  display_name: 'Warrior Level 2',
  xp_cost: 0,
  requirements_met: true,
  locked_reason: null,
  class_level_unlock_id: 42,
  class_name: 'Warrior',
  target_level: 2,
  thread_id: null,
  boundary_level: null,
  thread_name: null,
  thread_level: null,
  thread_resonance_id: null,
  thread_resonance_name: null,
  thread_target_kind: null,
  dev_points_to_boundary: null,
  skill_id: null,
};

function setupMocks(options?: { items?: (typeof item)[]; isLoading?: boolean }) {
  const mutate = vi.fn();

  vi.mocked(progressionQueries.useProgressionUnlocksQuery).mockReturnValue({
    data: { results: options?.items ?? [item] },
    isLoading: options?.isLoading ?? false,
    error: null,
  } as unknown as ReturnType<typeof useProgressionUnlocksQuery>);

  vi.mocked(progressionQueries.usePurchaseUnlockMutation).mockReturnValue({
    mutate,
    isPending: false,
    variables: undefined,
  } as unknown as ReturnType<typeof usePurchaseUnlockMutation>);

  return { mutate };
}

describe('ClassUnlocksCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('queries the class_level unlock type', () => {
    setupMocks();
    renderWithProviders(<ClassUnlocksCard />);
    expect(progressionQueries.useProgressionUnlocksQuery).toHaveBeenCalledWith('class_level');
  });

  it('renders the class/target-level extra line', () => {
    setupMocks();
    renderWithProviders(<ClassUnlocksCard />);
    expect(screen.getByText('Warrior Level 2')).toBeInTheDocument();
    expect(screen.getByText('Warrior → level 2')).toBeInTheDocument();
  });

  it('flags the exact zero-cost tuning gap from #3045 as "cost unset", never inventing a number', () => {
    setupMocks();
    renderWithProviders(<ClassUnlocksCard />);
    expect(screen.getByTestId('unlock-cost-unset')).toBeInTheDocument();
  });

  it('buying dispatches the purchase mutation with class_level_unlock_id', async () => {
    const { mutate } = setupMocks();
    renderWithProviders(<ClassUnlocksCard />);

    await userEvent.click(screen.getByTestId('unlock-buy-button'));

    expect(mutate).toHaveBeenCalledWith(
      { unlock_type: 'class_level', class_level_unlock_id: 42 },
      expect.anything()
    );
  });

  it('shows the empty state when no class unlocks are available', () => {
    setupMocks({ items: [] });
    renderWithProviders(<ClassUnlocksCard />);
    expect(screen.getByTestId('class-unlocks-empty')).toBeInTheDocument();
  });
});
