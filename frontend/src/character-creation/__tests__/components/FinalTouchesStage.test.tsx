/**
 * FinalTouchesStage Component Tests (folio, #3630)
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { FinalTouchesStage } from '../../components/FinalTouchesStage';
import { createMockDraft, mockCGExplanations } from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

vi.mock('../../goals', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../goals')>()),
  useGoalDomains: () => ({
    data: [
      {
        id: 1,
        name: 'Ambition',
        description: 'What you reach for.',
        display_order: 1,
        is_optional: false,
      },
    ],
    isLoading: false,
    error: null,
  }),
}));
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

describe('FinalTouchesStage (folio)', () => {
  it('shows the purse at the head and each domain as a group', () => {
    const draft = createMockDraft({
      draft_data: { goals: [{ domain_id: 1, notes: 'Rule the docks', points: 10 }] },
    });
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText(/Points remaining/)).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText('Ambition')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Rule the docks')).toBeInTheDocument();
  });

  it('adds a goal to a domain and marks the purse over when points exceed 30', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      draft_data: { goals: [{ domain_id: 1, notes: 'A', points: 30 }] },
    });
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    await user.click(screen.getByRole('button', { name: 'Add a goal' }));
    const points = screen.getAllByLabelText('Points')[1];
    await user.clear(points);
    await user.type(points, '5');
    expect(screen.getByText(/over by 5/)).toBeInTheDocument();
  });
});
