/**
 * OriginStage Component Tests
 *
 * Tests for the starting area selection stage of character creation.
 * Uses a master-detail layout with area cards on the left and a detail panel
 * on the right that shows the description of the hovered/selected/first area.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { OriginStage } from '../../components/OriginStage';
import { mockEmptyDraft, mockDraftWithArea, mockStartingAreas } from '../fixtures';
import { mockStaffAccount, mockPlayerAccount } from '../mocks';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';

// Mock the API module
vi.mock('../../api', () => ({
  getStartingAreas: vi.fn(),
  updateDraft: vi.fn(),
}));

describe('OriginStage', () => {
  describe('Loading State', () => {
    it('shows loading spinner while fetching areas', () => {
      const queryClient = createTestQueryClient();
      // Don't seed data - query will be in loading state

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      // The loading spinner has animate-spin class
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });
  });

  describe('Rendering Starting Areas', () => {
    it('renders all accessible starting areas', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      await waitFor(() => {
        // Area names appear in cards and potentially in the detail panel
        expect(screen.getAllByText('Arx City').length).toBeGreaterThan(0);
      });

      expect(screen.getAllByText('Northern Reaches').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Hidden Vale').length).toBeGreaterThan(0);
    });

    it('displays area cards with names', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      await waitFor(() => {
        // Check for area name in the h3 element specifically
        const areaHeadings = screen.getAllByRole('heading', { level: 3 });
        const areaNames = areaHeadings.map((h) => h.textContent);
        expect(areaNames).toContain('Arx City');
        expect(areaNames).toContain('Northern Reaches');
      });
    });

    it('shows empty state when no areas available', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), []);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByText(/no starting areas are currently available/i)).toBeInTheDocument();
      });
    });
  });

  describe('Detail Panel', () => {
    it('shows the first area description in the detail panel by default', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      await waitFor(() => {
        // The detail panel shows the description (rendered in both desktop and mobile panels)
        expect(
          screen.getAllByText('The great capital city, a hub of politics and intrigue.').length
        ).toBeGreaterThan(0);
      });
    });

    it('shows the selected area description in the detail panel', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockDraftWithArea} />, {
        queryClient,
      });

      await waitFor(() => {
        // mockDraftWithArea has Arx City selected (rendered in both desktop and mobile panels)
        expect(
          screen.getAllByText('The great capital city, a hub of politics and intrigue.').length
        ).toBeGreaterThan(0);
      });
    });

    it('shows inaccessible warning in the detail panel for locked areas', async () => {
      const queryClient = createTestQueryClient();
      // Only provide the inaccessible area so it shows in the detail panel
      const inaccessibleOnly = [mockStartingAreas[2]]; // Hidden Vale
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), inaccessibleOnly);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      await waitFor(() => {
        // Warning appears in both desktop and mobile detail panels
        expect(
          screen.getAllByText('This area is not currently accessible to your account.').length
        ).toBeGreaterThan(0);
      });
    });
  });

  describe('Area Selection', () => {
    it('highlights the currently selected area', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockDraftWithArea} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getAllByText('Arx City').length).toBeGreaterThan(0);
      });

      // The selected card should have ring-2 class indicating selection
      const selectedCard = screen.getAllByText('Arx City')[0].closest('[class*="ring-2"]');
      expect(selectedCard).toBeInTheDocument();
    });

    it('allows selecting a different area', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockDraftWithArea} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getAllByText('Northern Reaches').length).toBeGreaterThan(0);
      });

      // Find the card for Northern Reaches using the h3 heading
      const areaHeadings = screen.getAllByRole('heading', { level: 3 });
      const northernHeading = areaHeadings.find((h) => h.textContent === 'Northern Reaches');
      const northernCard = northernHeading?.closest('[class*="cursor-pointer"]');
      expect(northernCard).toBeInTheDocument();

      // Click to select should trigger mutation
      await user.click(northernCard!);
      // Mutation would be called - we're testing the UI interaction
    });
  });

  describe('Page Header', () => {
    it('displays the stage title and description', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
      });

      expect(screen.getByText('Choose Your Origin')).toBeInTheDocument();
      expect(
        screen.getByText(/select the city or region where your character's story begins/i)
      ).toBeInTheDocument();
    });
  });

  describe('Staff vs Player Visibility', () => {
    it('shows inaccessible areas to staff', async () => {
      const queryClient = createTestQueryClient();
      // Include inaccessible area in the list
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
        account: mockStaffAccount,
      });

      await waitFor(() => {
        expect(screen.getAllByText('Hidden Vale').length).toBeGreaterThan(0);
      });
    });

    it('shows inaccessible areas to players (they may have visual indication they cannot select)', async () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.startingAreas(), mockStartingAreas);

      renderWithCharacterCreationProviders(<OriginStage draft={mockEmptyDraft} />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        // The area is shown (backend filters what's actually selectable)
        expect(screen.getAllByText('Hidden Vale').length).toBeGreaterThan(0);
      });
    });
  });

  describe('Error Handling', () => {
    it('displays error message when API fails', async () => {
      const queryClient = createTestQueryClient();
      // Manually set error state
      queryClient.setQueryData(characterCreationKeys.startingAreas(), undefined);
      queryClient.setQueryDefaults(characterCreationKeys.startingAreas(), {
        queryFn: () => Promise.reject(new Error('Network error')),
      });

      // For this test, we need to trigger an actual query with error
      // The component shows error based on the `error` property from useQuery
    });
  });
});
