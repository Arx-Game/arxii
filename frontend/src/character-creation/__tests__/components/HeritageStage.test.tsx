/**
 * HeritageStage Component Tests
 *
 * Tests for heritage selection, species, gender, pronouns, and age.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { HeritageStage } from '../../components/HeritageStage';
import {
  mockBeginnings,
  mockBeginningsUnknownFamily,
  mockCGExplanations,
  mockDraftWithArea,
  mockDraftWithHeritage,
  mockEmptyDraft,
  mockStartingArea,
  mockSpeciesHuman,
  mockSpeciesElf,
  mockNobleFamily,
  mockNobleFamily2,
  mockCommonerFamily,
} from '../fixtures';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';
import { Stage } from '../../types';

// Mock the API module
vi.mock('../../api', () => ({
  getBeginnings: vi.fn(),
  getGenders: vi.fn(),
  getSpecies: vi.fn(),
  getCGPointBudget: vi.fn(),
  getFamiliesWithOpenKinSlots: vi.fn(),
  updateDraft: vi.fn(),
  getCGExplanations: vi.fn(),
  getBeginningsPerspectives: vi.fn(),
}));

// Mock CG Point Budget data
const mockCGBudget = {
  id: 1,
  name: 'Default Budget',
  starting_points: 100,
  is_active: true,
};

// Mock Species list
const mockSpeciesList = [mockSpeciesHuman, mockSpeciesElf];

// Mock Families list (for family selection)
const mockFamilies = [mockNobleFamily, mockNobleFamily2, mockCommonerFamily];

// Mock Beginnings list
const mockBeginningsList = [mockBeginnings, mockBeginningsUnknownFamily];

// Mock Genders list
const mockGenders = [
  { id: 1, key: 'male', display_name: 'Male' },
  { id: 2, key: 'female', display_name: 'Female' },
  { id: 3, key: 'non-binary', display_name: 'Non-binary' },
];

describe('HeritageStage', () => {
  const mockOnStageSelect = vi.fn();

  // Helper function to seed all required query data for HeritageStage
  function seedHeritageStageData(queryClient: ReturnType<typeof createTestQueryClient>) {
    seedQueryData(queryClient, characterCreationKeys.cgBudget(), mockCGBudget);
    seedQueryData(
      queryClient,
      characterCreationKeys.beginnings(mockStartingArea.id),
      mockBeginningsList
    );
    seedQueryData(queryClient, characterCreationKeys.species(), mockSpeciesList);
    seedQueryData(
      queryClient,
      characterCreationKeys.familiesWithOpenKinSlots(mockStartingArea.id),
      mockFamilies
    );
    seedQueryData(queryClient, characterCreationKeys.genders(), mockGenders);
    seedQueryData(queryClient, characterCreationKeys.explanations(), mockCGExplanations);
  }

  beforeEach(() => {
    mockOnStageSelect.mockClear();
  });

  describe('No Area Selected', () => {
    it('prompts user to select area first', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockEmptyDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText(/please select a starting area first/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /go to origin selection/i })).toBeInTheDocument();
    });

    it('navigates back to Origin stage when button clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockEmptyDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /go to origin selection/i });
      await user.click(button);

      expect(mockOnStageSelect).toHaveBeenCalledWith(Stage.ORIGIN);
    });
  });

  describe('Beginnings Selection', () => {
    it('shows normal upbringing option', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        // Name appears in both the card and the detail panel
        expect(screen.getAllByText('Normal Upbringing').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows sleeper beginnings option when available', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Sleeper')).toBeInTheDocument();
      });

      expect(
        screen.getByText(/awakened from magical slumber with no memory of origins/i)
      ).toBeInTheDocument();
    });

    it('highlights selected beginnings', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        // "Sleeper" appears both as the entry name and in the record rail;
        // target the entry (folio markup marks the chosen entry `li.chosen`).
        const cards = screen.getAllByText('Sleeper');
        const beginningsEntry = cards
          .map((el) => el.closest('li'))
          .find((el) => el?.classList.contains('chosen'));
        expect(beginningsEntry).toBeTruthy();
      });
    });

    it('shows species section only after beginnings selected', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);
      // Draft without selected_beginnings
      const draftNoBeginnings = {
        ...mockDraftWithArea,
        selected_beginnings: null,
      };

      renderWithCharacterCreationProviders(
        <HeritageStage draft={draftNoBeginnings} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        // The record rail also carries a "Beginnings" row label, so target
        // the section heading specifically (folio markup).
        expect(screen.getByRole('heading', { name: 'Beginnings' })).toBeInTheDocument();
      });

      // Species section should not appear until beginnings is selected. The
      // record rail always carries a "Species" row label, so target the
      // section heading specifically.
      expect(screen.queryByRole('heading', { name: 'Species' })).not.toBeInTheDocument();
    });
  });

  describe('Species Selection', () => {
    it('shows species cards', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Species' })).toBeInTheDocument();
      });

      // Should show species cards
      expect(screen.getByText('Human')).toBeInTheDocument();
      expect(screen.getByText('Elf')).toBeInTheDocument();
    });

    it('shows loading state while fetching species', () => {
      const queryClient = createTestQueryClient();
      // Seed CG budget and families but not species - should show loading
      seedQueryData(queryClient, characterCreationKeys.cgBudget(), mockCGBudget);
      seedQueryData(
        queryClient,
        characterCreationKeys.familiesWithOpenKinSlots(mockStartingArea.id),
        mockFamilies
      );

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      // Loading state: the folio stage gates its whole body behind one
      // ledger line while any of beginnings/species/genders is loading,
      // rather than a per-section skeleton.
      expect(screen.getByText(/loading heritage/i)).toBeInTheDocument();
    });
  });

  describe('Gender Selection', () => {
    it('shows all gender options', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Male' })).toBeInTheDocument();
      });

      expect(screen.getByRole('button', { name: 'Female' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Non-binary' })).toBeInTheDocument();
    });

    it('highlights currently selected gender', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        const femaleButton = screen.getByRole('button', { name: 'Female' });
        // ChoiceRow marks the pressed option via aria-pressed (folio markup).
        expect(femaleButton).toHaveAttribute('aria-pressed', 'true');
      });
    });
  });

  describe('Perspectives Panel', () => {
    it('shows the beginnings perspective opinion for the selected beginning', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);
      seedQueryData(queryClient, characterCreationKeys.beginningsPerspectives(mockBeginnings.id), [
        {
          entry_id: 1,
          name: 'Duskborn Doorways',
          summary: 'They talk to doors.',
          lore_content: 'Every Duskborn home has a second door no guest may use.',
          subject_name: 'The Duskborn',
        },
      ]);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        // The detail panel renders in both the desktop and mobile layout.
        expect(screen.getAllByText('On The Duskborn').length).toBeGreaterThanOrEqual(1);
      });
      expect(
        screen.getAllByText('Every Duskborn home has a second door no guest may use.').length
      ).toBeGreaterThanOrEqual(1);
    });

    it('does not show a Perspectives heading when the endpoint returns none', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);
      seedQueryData(
        queryClient,
        characterCreationKeys.beginningsPerspectives(mockBeginnings.id),
        []
      );

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getAllByText('Normal Upbringing').length).toBeGreaterThanOrEqual(1);
      });
      expect(screen.queryByText('Perspectives')).not.toBeInTheDocument();
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Heritage')).toBeInTheDocument();
      expect(
        screen.getByText(/define your character's beginnings, species, and identity/i)
      ).toBeInTheDocument();
    });
  });

  describe('Folio markup', () => {
    it('lists beginnings as entries with their point cost as the tag and no hover panel', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);
      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );
      const list = await screen.findByRole('list', { name: 'Beginnings' });
      expect(within(list).getByText(mockBeginnings.name)).toBeInTheDocument();
      expect(within(list).getAllByText(/no cost/i).length).toBeGreaterThan(0);
      expect(screen.queryByText(/hover/i)).not.toBeInTheDocument();
    });

    it("links a beginning's name to its codex entry only when one exists", async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);
      const beginningWithCodex = {
        ...mockBeginnings,
        id: 10,
        name: 'Duskborn Rite',
        codex_entry_ids: [7],
      };
      const beginningWithoutCodex = {
        ...mockBeginningsUnknownFamily,
        id: 11,
        codex_entry_ids: [],
      };
      seedQueryData(queryClient, characterCreationKeys.beginnings(mockStartingArea.id), [
        beginningWithCodex,
        beginningWithoutCodex,
      ]);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      const list = await screen.findByRole('list', { name: 'Beginnings' });
      expect(within(list).getByText('Codex: Duskborn Rite')).toBeInTheDocument();
      // Only the entry with a codex entry id gets a "Codex:" line.
      expect(within(list).getAllByText(/^Codex:/).length).toBe(1);
    });

    it('lists the chosen values in the rail and offers gender as a pressed row', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);
      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );
      const rail = await screen.findByRole('heading', { name: 'Your choices so far' });
      expect(rail).toBeInTheDocument();
      expect(screen.getByRole('group', { name: 'Gender' })).toBeInTheDocument();
    });
  });
});
