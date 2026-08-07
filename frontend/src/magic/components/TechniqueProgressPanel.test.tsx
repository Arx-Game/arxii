/**
 * TechniqueProgressPanel tests (#2739 Task 3) — player-facing training-meter list.
 *
 * Mirrors MotifStylePanel.test.tsx's mock-the-hook-module idiom (no msw).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { TechniqueProgressPanel } from './TechniqueProgressPanel';
import type { useTechniqueProgress, useTrainTechnique } from '../queries';

vi.mock('../queries', () => ({
  useTechniqueProgress: vi.fn(),
  useTrainTechnique: vi.fn(),
}));

import * as magicQueries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockMeters = [
  {
    id: 1,
    technique_id: 11,
    technique_name: 'Cinderline Draw',
    points_accumulated: 4,
    total_required: 10,
    teacher_name: 'Ariel',
    source_label: 'Teaching Offer',
    weekly_remaining: 30,
  },
  {
    id: 2,
    technique_id: 22,
    technique_name: 'Hollow Step',
    points_accumulated: 8,
    total_required: 8,
    teacher_name: null,
    source_label: 'Academy Training',
    weekly_remaining: null,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupMocks(options?: {
  meters?: typeof mockMeters;
  isLoading?: boolean;
  trainOverrides?: { isPending?: boolean; isError?: boolean; error?: Error | null };
}) {
  const trainMutate = vi.fn();

  vi.mocked(magicQueries.useTechniqueProgress).mockReturnValue({
    data: options?.meters ?? mockMeters,
    isLoading: options?.isLoading ?? false,
  } as unknown as ReturnType<typeof useTechniqueProgress>);

  vi.mocked(magicQueries.useTrainTechnique).mockReturnValue({
    mutate: trainMutate,
    isPending: options?.trainOverrides?.isPending ?? false,
    isError: options?.trainOverrides?.isError ?? false,
    error: options?.trainOverrides?.error ?? null,
  } as unknown as ReturnType<typeof useTrainTechnique>);

  return { trainMutate };
}

describe('TechniqueProgressPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders each meter with progress fraction, teacher, and weekly remaining', () => {
    setupMocks({});
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    const rows = screen.getAllByTestId('technique-progress-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Cinderline Draw');
    expect(rows[0]).toHaveTextContent('4/10');
    expect(rows[0]).toHaveTextContent('Taught by Ariel');
    expect(rows[0]).toHaveTextContent('30 AP left this week');

    expect(rows[1]).toHaveTextContent('Hollow Step');
    expect(rows[1]).toHaveTextContent('Self-study');
  });

  it('scopes the meter list and mutation to the viewed character', () => {
    setupMocks({});
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    expect(magicQueries.useTechniqueProgress).toHaveBeenCalledWith(10);
    expect(magicQueries.useTrainTechnique).toHaveBeenCalledWith(10);
  });

  it('shows a quiet empty state when there are no meters', () => {
    setupMocks({ meters: [] });
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    expect(screen.getByTestId('technique-progress-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('technique-progress-row')).not.toBeInTheDocument();
  });

  it('fires the train mutation with no body when the AP input is left blank', async () => {
    const { trainMutate } = setupMocks({});
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    await userEvent.click(screen.getByTestId('technique-progress-train-11'));

    expect(trainMutate).toHaveBeenCalledWith(
      { techniqueId: 11, body: undefined },
      expect.anything()
    );
  });

  it('fires the train mutation with ap_to_invest when the AP input is filled in', async () => {
    const { trainMutate } = setupMocks({});
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    await userEvent.type(screen.getByTestId('technique-progress-ap-input-11'), '3');
    await userEvent.click(screen.getByTestId('technique-progress-train-11'));

    expect(trainMutate).toHaveBeenCalledWith(
      { techniqueId: 11, body: { ap_to_invest: 3 } },
      expect.anything()
    );
  });

  it('renders the training-session outcome after a successful train call', async () => {
    const { trainMutate } = setupMocks({});
    trainMutate.mockImplementation((_variables, { onSuccess }) => {
      onSuccess({
        technique_id: 11,
        outcome_name: 'Solid Progress',
        points_before: 4,
        points_after: 6,
        total_required: 10,
        technique_acquired: false,
        self_study: false,
      });
    });
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    await userEvent.click(screen.getByTestId('technique-progress-train-11'));

    expect(screen.getByTestId('technique-progress-result-11')).toHaveTextContent(
      'Solid Progress: 6/10.'
    );
  });

  it('renders the 400 detail message on a training error', async () => {
    const { trainMutate } = setupMocks({
      trainOverrides: { isError: true, error: new Error('Weekly training cap reached.') },
    });
    trainMutate.mockImplementation((_variables, { onError }) => {
      onError();
    });
    renderWithProviders(<TechniqueProgressPanel characterSheetId={10} />);

    await userEvent.click(screen.getByTestId('technique-progress-train-11'));

    expect(screen.getByTestId('technique-progress-error-11')).toHaveTextContent(
      'Weekly training cap reached.'
    );
  });
});
