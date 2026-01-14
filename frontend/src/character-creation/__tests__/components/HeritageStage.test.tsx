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

describe('HeritageStage', () => {
  const mockOnStageSelect = vi.fn();

  // Helper function to seed all required query data for HeritageStage
  function seedHeritageStageData(queryClient: ReturnType<typeof createTestQueryClient>) {
    seedQueryData(queryClient, characterCreationKeys.cgBudget(), mockCGBudget);
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

  describe('Heritage Type Selection', () => {
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

    it('shows special heritage options when available', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Fae-Touched')).toBeInTheDocument();
      });

      expect(screen.getByText(/born with a connection to the fae realms/i)).toBeInTheDocument();
    });

    it('highlights selected heritage type', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        const heritageCard = screen.getByText('Fae-Touched').closest('[class*="cursor-pointer"]');
        expect(heritageCard).toHaveClass('ring-2');
      });
    });

    it('does not show heritage section if no special heritages available', async () => {
      const queryClient = createTestQueryClient();
      const draftNoHeritages = {
        ...mockDraftWithArea,
        selected_area: {
          ...mockStartingArea,
          special_heritages: [],
        },
      };
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={draftNoHeritages} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Species & Origin')).toBeInTheDocument();
      });

      // Heritage type section should not appear
      expect(screen.queryByText('Heritage Type')).not.toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: 'Other' })).toBeInTheDocument();
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

  describe('Pronouns Section', () => {
    it('displays pronoun inputs', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Pronouns')).toBeInTheDocument();
      });

      expect(screen.getByText(/customize how your character is referred to/i)).toBeInTheDocument();
    });

    it('shows current pronoun values when set', async () => {
      const queryClient = createTestQueryClient();
      seedHeritageStageData(queryClient);

      renderWithCharacterCreationProviders(
        <HeritageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        // Check that pronoun inputs have the expected values
        const subjectInput = screen.getByDisplayValue('she');
        expect(subjectInput).toBeInTheDocument();
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

      expect(screen.getByText('Heritage & Lineage')).toBeInTheDocument();
      expect(
        screen.getByText(/define your character's origins, species, identity, and family/i)
      ).toBeInTheDocument();
    });
  });
});
