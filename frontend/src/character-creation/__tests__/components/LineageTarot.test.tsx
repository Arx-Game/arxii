/**
 * LineageTarot Component Tests
 *
 * Tests for tarot naming ritual visibility in the Lineage stage.
 * The naming ritual should appear for:
 * - Unknown origins (family_known = false)
 * - Orphans (is_orphan = true)
 * And should NOT appear when a character has a family selected.
 */

import { screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { LineageStage } from '../../components/LineageStage';
import type { TarotCard } from '../../types';
import {
  createMockDraft,
  mockBeginnings,
  mockBeginningsUnknownFamily,
  mockCGExplanations,
  mockDraftWithArea,
  mockDraftWithFamily,
  mockDraftWithHeritage,
  mockFamilies,
  mockStartingArea,
} from '../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';

// Mock the API module
vi.mock('../../api', () => ({
  getFamilies: vi.fn(),
  updateDraft: vi.fn(),
  getTarotCards: vi.fn(),
  getNamingRitualConfig: vi.fn(),
  getCGExplanations: vi.fn(),
}));

// =============================================================================
// Mock Tarot Card Data
// =============================================================================

const mockTarotCards: TarotCard[] = [
  {
    id: 1,
    name: 'The Fool',
    arcana_type: 'major',
    suit: null,
    rank: 0,
    latin_name: 'Stultus',
    description: 'New beginnings, innocence, spontaneity.',
    description_reversed: 'Recklessness, taken advantage of, inconsideration.',
    surname_upright: 'Stultus',
    surname_reversed: 'Vecors',
  },
  {
    id: 2,
    name: 'The Magician',
    arcana_type: 'major',
    suit: null,
    rank: 1,
    latin_name: 'Magus',
    description: 'Willpower, desire, resourcefulness.',
    description_reversed: 'Manipulation, poor planning, untapped talents.',
    surname_upright: 'Magus',
    surname_reversed: 'Praestigiator',
  },
  {
    id: 3,
    name: 'Ace of Swords',
    arcana_type: 'minor',
    suit: 'swords',
    rank: 1,
    latin_name: 'Gladius',
    description: 'Clarity, breakthrough, new ideas.',
    description_reversed: 'Confusion, brutality, chaos.',
    surname_upright: 'Sword',
    surname_reversed: 'Sword',
  },
  {
    id: 4,
    name: 'Two of Cups',
    arcana_type: 'minor',
    suit: 'cups',
    rank: 2,
    latin_name: 'Calix',
    description: 'Partnership, unity, attraction.',
    description_reversed: 'Imbalance, broken communication, tension.',
    surname_upright: 'Cup',
    surname_reversed: 'Cup',
  },
];

const mockNamingRitualConfig = {
  flavor_text: 'A Mirrormask draws from the Arcana to divine your name...',
  codex_entry_id: null,
};

describe('LineageTarot - Tarot Naming Ritual', () => {
  const mockOnStageSelect = vi.fn();

  beforeEach(() => {
    mockOnStageSelect.mockClear();
  });

  describe('Tarot section visibility', () => {
    it('does NOT appear when character has a family', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), mockTarotCards);
      seedQueryData(queryClient, characterCreationKeys.explanations(), mockCGExplanations);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithFamily} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Lineage')).toBeInTheDocument();
      });

      expect(screen.queryByText('Naming Ritual')).not.toBeInTheDocument();
    });

    it('appears for unknown origins (family_known = false)', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), mockTarotCards);
      seedQueryData(
        queryClient,
        characterCreationKeys.namingRitualConfig(),
        mockNamingRitualConfig
      );

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Naming Ritual')).toBeInTheDocument();
      });
    });

    it('appears for orphans (is_orphan = true)', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), mockTarotCards);
      seedQueryData(
        queryClient,
        characterCreationKeys.namingRitualConfig(),
        mockNamingRitualConfig
      );

      const orphanDraft = createMockDraft({
        ...mockDraftWithArea,
        is_orphan: true,
        family: null,
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={orphanDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Naming Ritual')).toBeInTheDocument();
      });
    });

    it('does NOT appear for non-orphan with normal beginnings', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), mockTarotCards);
      seedQueryData(queryClient, characterCreationKeys.explanations(), mockCGExplanations);

      const normalDraft = createMockDraft({
        ...mockDraftWithArea,
        is_orphan: false,
        family: null,
        selected_beginnings: mockBeginnings,
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={normalDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Lineage')).toBeInTheDocument();
      });

      expect(screen.queryByText('Naming Ritual')).not.toBeInTheDocument();
    });
  });

  describe('Tarot section content', () => {
    function seedTarotQueries(queryClient: ReturnType<typeof createTestQueryClient>) {
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), mockTarotCards);
      seedQueryData(
        queryClient,
        characterCreationKeys.namingRitualConfig(),
        mockNamingRitualConfig
      );
    }

    it('shows the Draw Random Card button', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /draw random card/i })).toBeInTheDocument();
      });
    });

    it('displays major arcana card names', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('The Fool')).toBeInTheDocument();
        expect(screen.getByText('The Magician')).toBeInTheDocument();
      });
    });

    it('displays minor arcana sections by suit', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Minor Arcana')).toBeInTheDocument();
      });

      expect(screen.getByText('Ace of Swords')).toBeInTheDocument();
      expect(screen.getByText('Two of Cups')).toBeInTheDocument();
    });

    it('shows flavor text for the naming ritual', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(
          screen.getByText(/a mirrormask draws from the arcana to divine your name/i)
        ).toBeInTheDocument();
      });
    });

    it('shows custom flavor text from ritual config', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), mockTarotCards);
      seedQueryData(queryClient, characterCreationKeys.namingRitualConfig(), {
        flavor_text: 'The cards whisper your true name...',
        codex_entry_id: null,
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('The cards whisper your true name...')).toBeInTheDocument();
      });
    });

    it('shows prompt to draw a card when none selected', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText(/draw a card to determine your surname/i)).toBeInTheDocument();
      });
    });

    it('shows surname preview when a card is pre-selected', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      const draftWithTarot = createMockDraft({
        ...mockDraftWithHeritage,
        selected_beginnings: mockBeginningsUnknownFamily,
        draft_data: {
          tarot_card_name: 'The Fool',
          tarot_reversed: false,
        },
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draftWithTarot} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText(/your surname:/i)).toBeInTheDocument();
      });

      // Verify the surname text appears (in both preview and card list)
      const surnameElements = screen.getAllByText(/stultus/i);
      expect(surnameElements.length).toBeGreaterThanOrEqual(1);
    });

    it('shows reversed description for selected reversed Major Arcana card', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      const draftWithReversed = createMockDraft({
        ...mockDraftWithHeritage,
        selected_beginnings: mockBeginningsUnknownFamily,
        draft_data: {
          tarot_card_name: 'The Fool',
          tarot_reversed: true,
        },
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draftWithReversed} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(
          screen.getByText(/recklessness, taken advantage of, inconsideration/i)
        ).toBeInTheDocument();
      });
    });

    it('shows full name preview when first_name is set', async () => {
      const queryClient = createTestQueryClient();
      seedTarotQueries(queryClient);

      const draftWithName = createMockDraft({
        ...mockDraftWithHeritage,
        selected_beginnings: mockBeginningsUnknownFamily,
        draft_data: {
          first_name: 'Aldric',
          tarot_card_name: 'The Fool',
          tarot_reversed: false,
        },
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draftWithName} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Aldric Stultus')).toBeInTheDocument();
      });
    });
  });
});
