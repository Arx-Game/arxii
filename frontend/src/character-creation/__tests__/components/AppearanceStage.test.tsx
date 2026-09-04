/**
 * AppearanceStage Component Tests (folio, #3630)
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { AppearanceStage } from '../../components/AppearanceStage';
import {
  createMockDraft,
  mockBuildAthletic,
  mockBuildAverage,
  mockCGExplanations,
  mockHeightBandAverage,
  mockHeightBandTall,
  mockSpeciesHuman,
} from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

const mutate = vi.fn();
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate, mutateAsync: vi.fn() }),
  useHeightBands: () => ({ data: [mockHeightBandAverage, mockHeightBandTall], isLoading: false }),
  useBuilds: () => ({ data: [mockBuildAverage, mockBuildAthletic], isLoading: false }),
  useFormOptions: () => ({
    data: {
      traits: [
        {
          trait: { id: 1, name: 'hair_color', display_name: 'Hair color', trait_type: 'color' },
          is_required: true,
          options: [{ id: 5, name: 'black', display_name: 'Black', sort_order: 1 }],
        },
      ],
      inherited: [],
    },
    isLoading: false,
  }),
}));
vi.mock('../../api', () => ({
  listDraftMarkings: vi.fn().mockResolvedValue([]),
  createDraftMarking: vi.fn(),
  deleteDraftMarking: vi.fn(),
}));

describe('AppearanceStage (folio)', () => {
  const draft = createMockDraft({
    selected_species: mockSpeciesHuman,
    height_band: mockHeightBandAverage,
    height_inches: 68,
  });
  const props = { draft, onRegisterBeforeLeave: vi.fn() } as const;

  it('offers height band and build as pressed rows and age as a field', () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByRole('group', { name: 'Height band' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Build' })).toBeInTheDocument();
    expect(screen.getByLabelText('Age')).toHaveAttribute('type', 'number');
  });

  it('writes a form trait choice into draft_data.form_traits', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    await user.click(screen.getByRole('button', { name: 'Black' }));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            form_traits: expect.objectContaining({ hair_color: 5 }),
          }),
        }),
      })
    );
  });
});
