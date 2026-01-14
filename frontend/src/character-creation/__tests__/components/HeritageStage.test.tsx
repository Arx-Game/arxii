/**
 * HeritageStage Component Tests
 *
 * Tests for heritage selection, species, gender, pronouns, and age.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { HeritageStage } from '../../components/HeritageStage';
import {
  mockBeginnings,
  mockBeginningsUnknownFamily,
  mockDraftWithArea,
  mockDraftWithHeritage,
  mockEmptyDraft,
  mockStartingArea,
  mockSpeciesOptionHuman,
  mockSpeciesOptionElf,
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
  getSpeciesOptions: vi.fn(),
  getCGPointBudget: vi.fn(),
  getFamiliesWithOpenPositions: vi.fn(),
  getFamilyTree: vi.fn(),
  createFamily: vi.fn(),
  updateDraft: vi.fn(),
}));

// Mock CG Point Budget data
const mockCGBudget = {
  id: 1,
  name: 'Default Budget',
  starting_points: 100,
  is_active: true,
};

// Mock Species Options list
const mockSpeciesOptions = [mockSpeciesOptionHuman, mockSpeciesOptionElf];

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
    seedQueryData(
      queryClient,
      characterCreationKeys.speciesOptions(mockStartingArea.id),
      mockSpeciesOptions
    );
    seedQueryData(
      queryClient,
      characterCreationKeys.familiesWithOpenPositions(mockStartingArea.id),
      mockFamilies
    );
    seedQueryData(queryClient, characterCreationKeys.genders(), mockGenders);
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
        expect(screen.getByText('Normal Upbringing')).toBeInTheDocument();
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
        const beginningsCard = screen.getByText('Sleeper').closest('[class*="cursor-pointer"]');
        expect(beginningsCard).toHaveClass('ring-2');
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
        expect(screen.getByText('Beginnings')).toBeInTheDocument();
      });

      // Species section should not appear until beginnings is selected
      expect(screen.queryByText('Species & Origin')).not.toBeInTheDocument();
    });
  });

  describe('Species Selection', () => {
    it('shows species option cards', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Species & Origin')).toBeInTheDocument();
      });

      // Should show species option cards
      expect(screen.getByText('Human')).toBeInTheDocument();
      expect(screen.getByText('Elf')).toBeInTheDocument();
    });

    it('shows loading state while fetching species', () => {
      const queryClient = createTestQueryClient();
      // Seed CG budget and families but not species options - should show loading
      seedQueryData(queryClient, characterCreationKeys.cgBudget(), mockCGBudget);
      seedQueryData(
        queryClient,
        characterCreationKeys.familiesWithOpenPositions(mockStartingArea.id),
        mockFamilies
      );

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      // Loading state for species options
      expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
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
        // Selected button should have default variant (not outline)
        expect(femaleButton).not.toHaveClass('border-input');
      });
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
});
