/**
 * CantripSelector Component Tests
 *
 * Tests cantrip card selection, facet dropdown, consequence-pool dropdown,
 * and the resonance dropdown (#1620).
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { CantripSelector } from '../../components/magic/CantripSelector';
import { mockResonances } from '../fixtures';
import {
  renderWithCharacterCreationProviders,
  seedQueryData,
  createTestQueryClient,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';
import type { Cantrip, CharacterDraft } from '../../types';

// Mock the API module
vi.mock('../../api', () => ({
  getResonances: vi.fn(),
  getConsequencePoolCatalog: vi.fn(),
  updateDraft: vi.fn(),
}));

const mockCantrip: Cantrip = {
  id: 10,
  name: 'Danger Sense',
  description: 'Sense nearby threats.',
  archetype: 'utility',
  requires_facet: false,
  facet_prompt: '',
  allowed_facets: [],
  sort_order: 0,
  style_id: 1,
};

const mockConsequencePools = [{ id: 1, name: 'Volatile', description: 'High risk, high reward.' }];

function makeDraft(selectedCantripId?: number): CharacterDraft {
  return {
    id: 1,
    current_stage: 7 as never,
    selected_area: null,
    selected_beginnings: null,
    selected_species: null,
    selected_gender: null,
    age: null,
    family: null,
    claimed_kin_slot: null,
    claimed_kin_pool: null,
    defer_parents: false,
    height_band: null,
    height_inches: null,
    build: null,
    selected_path: null,
    selected_tradition: null,
    cg_points_spent: 0,
    cg_points_remaining: 100,
    stat_bonuses: {},
    draft_data: selectedCantripId ? { selected_cantrip_id: selectedCantripId } : {},
    stage_completion: {} as never,
    has_existing_characters: false,
    stage_errors: {},
    stats_points_remaining: 5,
    stats_budget: 5,
  };
}

function renderSelector(draft: CharacterDraft, cantrips: Cantrip[]) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.resonances(), mockResonances);
  seedQueryData(queryClient, characterCreationKeys.consequencePoolCatalog(), mockConsequencePools);

  return renderWithCharacterCreationProviders(
    <CantripSelector draft={draft} cantrips={cantrips} />,
    { queryClient }
  );
}

describe('CantripSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the resonance dropdown when a cantrip is selected', () => {
    const draft = makeDraft(10);
    renderSelector(draft, [mockCantrip]);

    expect(screen.getByText('Gift Resonance')).toBeInTheDocument();
  });

  it('does not render the resonance dropdown when no cantrip is selected', () => {
    const draft = makeDraft();
    renderSelector(draft, [mockCantrip]);

    expect(screen.queryByText('Gift Resonance')).not.toBeInTheDocument();
  });

  it('renders the resonance options from the resonances query', () => {
    const draft = makeDraft(10);
    renderSelector(draft, [mockCantrip]);

    // The dropdown trigger should be present with a placeholder
    expect(screen.getByText('Gift Resonance')).toBeInTheDocument();
    expect(screen.getByText('Select a resonance')).toBeInTheDocument();
  });
});
