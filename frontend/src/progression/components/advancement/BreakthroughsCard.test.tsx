/**
 * BreakthroughsCard tests (#3045). Mocks `@/progression/queries` (no msw) —
 * mirrors MotifStylePanel.test.tsx's idiom.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { BreakthroughsCard } from './BreakthroughsCard';
import type { useProgressionUnlocksQuery, usePurchaseUnlockMutation } from '@/progression/queries';
import type { ProgressionUnlockItem } from '@/progression/types';

vi.mock('@/progression/queries', () => ({
  useProgressionUnlocksQuery: vi.fn(),
  usePurchaseUnlockMutation: vi.fn(),
}));

import * as progressionQueries from '@/progression/queries';

const authoredItem: ProgressionUnlockItem = {
  unlock_type: 'skill_breakthrough',
  display_name: 'Swordplay Breakthrough to 2.0',
  xp_cost: 75,
  requirements_met: true,
  locked_reason: null,
  class_level_unlock_id: null,
  class_name: null,
  target_level: null,
  thread_id: null,
  boundary_level: null,
  thread_name: null,
  thread_level: null,
  thread_resonance_id: null,
  thread_resonance_name: null,
  thread_target_kind: null,
  dev_points_to_boundary: null,
  skill_id: 5,
};

const unauthoredItem = {
  ...authoredItem,
  display_name: 'Larceny Breakthrough to 2.0',
  xp_cost: 0,
  requirements_met: false,
  locked_reason: 'Not yet authored',
  skill_id: 9,
};

function setupMocks(options?: {
  items?: (typeof authoredItem)[];
  isLoading?: boolean;
  isError?: boolean;
  purchaseOverrides?: { isPending?: boolean; variables?: unknown };
}) {
  const mutate = vi.fn();

  vi.mocked(progressionQueries.useProgressionUnlocksQuery).mockReturnValue({
    data: { results: options?.items ?? [authoredItem] },
    isLoading: options?.isLoading ?? false,
    error: options?.isError ? new Error('failed') : null,
  } as unknown as ReturnType<typeof useProgressionUnlocksQuery>);

  vi.mocked(progressionQueries.usePurchaseUnlockMutation).mockReturnValue({
    mutate,
    isPending: options?.purchaseOverrides?.isPending ?? false,
    variables: options?.purchaseOverrides?.variables,
  } as unknown as ReturnType<typeof usePurchaseUnlockMutation>);

  return { mutate };
}

describe('BreakthroughsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('queries the skill_breakthrough unlock type', () => {
    setupMocks();
    renderWithProviders(<BreakthroughsCard />);
    expect(progressionQueries.useProgressionUnlocksQuery).toHaveBeenCalledWith(
      'skill_breakthrough'
    );
  });

  it('renders an eligible breakthrough with its cost', () => {
    setupMocks();
    renderWithProviders(<BreakthroughsCard />);
    expect(screen.getByText('Swordplay Breakthrough to 2.0')).toBeInTheDocument();
    expect(screen.getByText('75 XP')).toBeInTheDocument();
    expect(screen.getByTestId('unlock-buy-button')).toBeEnabled();
  });

  it('shows the empty state when nothing is parked at a boundary', () => {
    setupMocks({ items: [] });
    renderWithProviders(<BreakthroughsCard />);
    expect(screen.getByTestId('breakthroughs-empty')).toBeInTheDocument();
  });

  it('disables buy and shows the locked reason for an unauthored breakthrough', () => {
    setupMocks({ items: [unauthoredItem] });
    renderWithProviders(<BreakthroughsCard />);
    expect(screen.getByTestId('unlock-locked-reason')).toHaveTextContent('Not yet authored');
    expect(screen.getByTestId('unlock-buy-button')).toBeDisabled();
  });

  it('buying dispatches the purchase mutation with skill_id', async () => {
    const { mutate } = setupMocks();
    renderWithProviders(<BreakthroughsCard />);

    await userEvent.click(screen.getByTestId('unlock-buy-button'));

    expect(mutate).toHaveBeenCalledWith(
      { unlock_type: 'skill_breakthrough', skill_id: 5 },
      expect.anything()
    );
  });

  it('shows a "cost unset" marker instead of "0 XP" for an eligible free row', () => {
    setupMocks({ items: [{ ...authoredItem, xp_cost: 0 }] });
    renderWithProviders(<BreakthroughsCard />);
    expect(screen.getByTestId('unlock-cost-unset')).toHaveTextContent('Cost unset');
    expect(screen.queryByText('0 XP')).not.toBeInTheDocument();
  });
});
