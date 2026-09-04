/**
 * GiftStage Component Tests (#3630 folio)
 *
 * Covers the funnel-as-entries shell: step names/tags always render, later
 * steps stay gated (and their pickers unmounted) until the step before them
 * is done, and the motif field is present. The individual pickers
 * (TraditionPicker, GiftSelector, TechniqueSelector, AnimaCheckStep,
 * GlimpseSection) have their own test files.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { GiftStage } from '../../components/GiftStage';
import {
  createMockDraft,
  mockCGExplanations,
  mockPath,
  mockResonances,
  mockTradition,
} from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useResonances: () => ({ data: mockResonances, isLoading: false }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
  useTraditions: () => ({ data: [mockTradition], isLoading: false }),
  useSelectTradition: () => ({ mutate: vi.fn(), isPending: false }),
  useTraditionPerspectives: () => ({ data: [] }),
  useCGGifts: () => ({ data: [], isLoading: false }),
  useCGTechniqueOptions: () => ({ data: [], isLoading: false }),
  useGlimpseTags: () => ({ data: [], isLoading: false }),
  useSkills: () => ({ data: [] }),
  useStatDefinitions: () => ({ data: [] }),
  usePathSkillSuggestions: () => ({ data: [] }),
}));
vi.mock('@/hooks/useDistinctions', () => ({ useDraftDistinctions: () => ({ data: [] }) }));

describe('GiftStage (folio)', () => {
  it('shows the five steps as entries, later steps gated until the earlier is done', () => {
    const draft = createMockDraft({ selected_path: mockPath, selected_tradition: null });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const steps = screen.getByRole('list', { name: 'Gift steps' });
    expect(steps).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 5')).toBeInTheDocument();
    expect(screen.getByText('Choose a tradition first')).toBeInTheDocument();
  });

  it('offers the motif as a field', () => {
    const draft = createMockDraft({ selected_path: mockPath });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByLabelText(/motif/i)).toBeInTheDocument();
  });
});
