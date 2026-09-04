/**
 * LineageTarot Component Tests
 *
 * Tests for tarot naming ritual visibility in the Lineage stage (#3617).
 * The naming ritual renders on the resolved family path 'none' (an
 * Upbringing whose only, or currently selected, family path is 'none') and
 * should NOT appear on the 'claimed' or 'named' paths.
 */

import { screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { LineageStage } from '../../components/LineageStage';
import * as api from '../../api';
import type { TarotCard } from '../../types';
import {
  createMockDraft,
  mockDraftWithHeritage,
  mockNobleFamily,
  mockUpbringingClaim,
  mockUpbringingNamed,
} from '../fixtures';
import { createTestQueryClient, renderWithCharacterCreationProviders } from '../testUtils';

// Mock the API module
vi.mock('../../api', () => ({
  getFamilies: vi.fn(),
  getOriginTemplates: vi.fn().mockResolvedValue([]),
  getClaimableTitles: vi.fn().mockResolvedValue([]),
  getHouseClaim: vi.fn().mockResolvedValue(null),
  submitHouseClaim: vi.fn(),
  updateDraft: vi.fn(),
  getTarotCards: vi.fn(),
  getNamingRitualConfig: vi.fn(),
  getCGExplanations: vi.fn(),
  getFamilySlots: vi.fn().mockResolvedValue({ slots: [], pools: [] }),
  // Invented-parents card (#2815)
  getGenders: vi.fn().mockResolvedValue([]),
  getSpecies: vi.fn().mockResolvedValue([]),
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
    vi.mocked(api.getFamilies).mockResolvedValue([]);
    vi.mocked(api.getOriginTemplates).mockResolvedValue([]);
    vi.mocked(api.getTarotCards).mockResolvedValue([]);
    vi.mocked(api.getNamingRitualConfig).mockResolvedValue({
      flavor_text: '',
      codex_entry_id: null,
    });
    vi.mocked(api.getCGExplanations).mockResolvedValue({});
  });

  describe('Tarot section visibility', () => {
    it('does NOT appear on the claimed path with a family chosen', async () => {
      vi.mocked(api.getFamilies).mockResolvedValue([mockNobleFamily]);

      const draft = createMockDraft({
        ...mockDraftWithHeritage,
        selected_origin_template: mockUpbringingClaim,
        family_path: 'claimed',
        family: mockNobleFamily,
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draft} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText('Valardin')).toBeInTheDocument();
      });

      expect(screen.queryByText('Naming Ritual')).not.toBeInTheDocument();
    });

    it('appears for a none-path upbringing', async () => {
      vi.mocked(api.getTarotCards).mockResolvedValue(mockTarotCards);
      vi.mocked(api.getNamingRitualConfig).mockResolvedValue(mockNamingRitualConfig);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText('Naming Ritual')).toBeInTheDocument();
      });
    });

    it('does NOT appear on the named path with no family named yet', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritage,
        selected_origin_template: mockUpbringingNamed,
        family_path: 'named',
        family: null,
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draft} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByLabelText(/family name/i)).toBeInTheDocument();
      });

      expect(screen.queryByText('Naming Ritual')).not.toBeInTheDocument();
    });
  });

  describe('Tarot section content', () => {
    function seedTarotMocks() {
      vi.mocked(api.getTarotCards).mockResolvedValue(mockTarotCards);
      vi.mocked(api.getNamingRitualConfig).mockResolvedValue(mockNamingRitualConfig);
    }

    it('shows the Draw Random Card button', async () => {
      seedTarotMocks();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /draw random card/i })).toBeInTheDocument();
      });
    });

    it('displays major arcana card names', async () => {
      seedTarotMocks();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText('The Fool')).toBeInTheDocument();
        expect(screen.getByText('The Magician')).toBeInTheDocument();
      });
    });

    it('displays minor arcana sections by suit', async () => {
      seedTarotMocks();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText('Minor Arcana')).toBeInTheDocument();
      });

      expect(screen.getByText('Ace of Swords')).toBeInTheDocument();
      expect(screen.getByText('Two of Cups')).toBeInTheDocument();
    });

    it('shows flavor text for the naming ritual', async () => {
      seedTarotMocks();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(
          screen.getByText(/a mirrormask draws from the arcana to divine your name/i)
        ).toBeInTheDocument();
      });
    });

    it('shows custom flavor text from ritual config', async () => {
      vi.mocked(api.getTarotCards).mockResolvedValue(mockTarotCards);
      vi.mocked(api.getNamingRitualConfig).mockResolvedValue({
        flavor_text: 'The cards whisper your true name...',
        codex_entry_id: null,
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText('The cards whisper your true name...')).toBeInTheDocument();
      });
    });

    it('shows prompt to draw a card when none selected', async () => {
      seedTarotMocks();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText(/draw a card to determine your surname/i)).toBeInTheDocument();
      });
    });

    it('shows surname preview when a card is pre-selected', async () => {
      seedTarotMocks();

      const draftWithTarot = createMockDraft({
        ...mockDraftWithHeritage,
        draft_data: {
          tarot_card_name: 'The Fool',
          tarot_reversed: false,
        },
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draftWithTarot} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText(/your surname:/i)).toBeInTheDocument();
      });

      // Verify the surname text appears (in both preview and card list)
      const surnameElements = screen.getAllByText(/stultus/i);
      expect(surnameElements.length).toBeGreaterThanOrEqual(1);
    });

    it('shows reversed description for selected reversed Major Arcana card', async () => {
      seedTarotMocks();

      const draftWithReversed = createMockDraft({
        ...mockDraftWithHeritage,
        draft_data: {
          tarot_card_name: 'The Fool',
          tarot_reversed: true,
        },
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draftWithReversed} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(
          screen.getByText(/recklessness, taken advantage of, inconsideration/i)
        ).toBeInTheDocument();
      });
    });

    it('shows full name preview when first_name is set', async () => {
      seedTarotMocks();

      const draftWithName = createMockDraft({
        ...mockDraftWithHeritage,
        draft_data: {
          first_name: 'Aldric',
          tarot_card_name: 'The Fool',
          tarot_reversed: false,
        },
      });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draftWithName} onStageSelect={mockOnStageSelect} />,
        { queryClient: createTestQueryClient() }
      );

      await waitFor(() => {
        expect(screen.getByText('Aldric Stultus')).toBeInTheDocument();
      });
    });
  });
});
