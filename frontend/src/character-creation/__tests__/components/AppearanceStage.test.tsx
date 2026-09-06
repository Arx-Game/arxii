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
  mockBeginnings,
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

  it('states the age range from the draft payload and the world fact behind it (#3663)', () => {
    const misbegotten = createMockDraft({
      ...draft,
      age_min: 18,
      age_max: 20,
      selected_beginnings: {
        ...mockBeginnings,
        heritage: { name: 'Misbegotten', first_appeared_ic_year: 980 },
      },
    });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={misbegotten} />);
    expect(screen.getByText(/must be between 18 and 20 years\./)).toBeInTheDocument();
    expect(screen.getByText(/The first Misbegotten were born in 980 AS\./)).toBeInTheDocument();
  });

  it('says nothing about a heritage that has no anchor', () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByText(/must be between 18 and 65 years\./)).toBeInTheDocument();
    expect(screen.queryByText(/were born in/)).toBeNull();
  });

  it('clamps a typed age to the payload ceiling', async () => {
    const user = userEvent.setup();
    const misbegotten = createMockDraft({ ...draft, age: 19, age_min: 18, age_max: 20 });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={misbegotten} />);
    const age = screen.getByLabelText('Age');
    await user.clear(age);
    await user.type(age, '30');
    await user.tab();
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ age: 20 }) })
    );
  });
});
