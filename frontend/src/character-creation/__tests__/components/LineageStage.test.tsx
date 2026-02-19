/**
 * LineageStage Component Tests
 *
 * Tests for family selection, orphan option, and special heritage lineage handling.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { LineageStage } from '../../components/LineageStage';
import {
  mockDraftWithArea,
  mockDraftWithHeritage,
  mockDraftWithFamily,
  mockEmptyDraft,
  mockFamilies,
  mockStartingArea,
  createMockDraft,
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
  getFamilies: vi.fn(),
  updateDraft: vi.fn(),
  getTarotCards: vi.fn(),
  getNamingRitualConfig: vi.fn(),
}));

describe('LineageStage', () => {
  const mockOnStageSelect = vi.fn();

  beforeEach(() => {
    mockOnStageSelect.mockClear();
  });

  describe('No Area Selected', () => {
    it('prompts user to select area first', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockEmptyDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText(/please select a starting area first/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /go to origin selection/i })).toBeInTheDocument();
    });

    it('navigates back to Origin stage when button clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockEmptyDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /go to origin selection/i });
      await user.click(button);

      expect(mockOnStageSelect).toHaveBeenCalledWith(Stage.ORIGIN);
    });
  });

  describe('Unknown Family Origin', () => {
    it('shows unknown origins message when beginnings has family_known = false', async () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Unknown Origins')).toBeInTheDocument();
      });

      expect(
        screen.getByText(/your true family origins are shrouded in mystery/i)
      ).toBeInTheDocument();
    });

    it('does not show family selection when family is unknown', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritage} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Unknown Origins')).toBeInTheDocument();
      });

      // Family selection should not appear
      expect(screen.queryByText('Select Family')).not.toBeInTheDocument();
      expect(screen.queryByText('Valardin')).not.toBeInTheDocument();
    });
  });

  describe('Normal Lineage - Family Selection', () => {
    it('shows orphan option', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Orphan / No Family')).toBeInTheDocument();
      });

      expect(
        screen.getByText(/your character has no known family, or has been disowned/i)
      ).toBeInTheDocument();
    });

    it('shows noble families section', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Noble Houses')).toBeInTheDocument();
      });

      expect(screen.getByText('Valardin')).toBeInTheDocument();
      expect(screen.getByText('Velenosa')).toBeInTheDocument();
    });

    it('shows commoner families dropdown', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText('Commoner Families')).toBeInTheDocument();
      });

      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('highlights selected family', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithFamily} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        const familyCard = screen.getByText('Valardin').closest('[class*="cursor-pointer"]');
        expect(familyCard).toHaveClass('ring-2');
      });
    });

    it('highlights orphan option when selected', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

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
        const orphanCard = screen
          .getByText('Orphan / No Family')
          .closest('[class*="cursor-pointer"]');
        expect(orphanCard).toHaveClass('ring-2');
      });
    });

    it('hides family selection when orphan is selected', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

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
        expect(screen.getByText('Orphan / No Family')).toBeInTheDocument();
      });

      // Family selection should be hidden
      expect(screen.queryByText('Select Family')).not.toBeInTheDocument();
      expect(screen.queryByText('Noble Houses')).not.toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('shows loading state while fetching families', () => {
      const queryClient = createTestQueryClient();
      // Don't seed families data - should show loading

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('shows message when no families available', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), []);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByText(/no families available for this area/i)).toBeInTheDocument();
      });
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.families(mockStartingArea.id), mockFamilies);

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithArea} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Lineage')).toBeInTheDocument();
      expect(screen.getByText(/choose your character's family/i)).toBeInTheDocument();
    });
  });
});
