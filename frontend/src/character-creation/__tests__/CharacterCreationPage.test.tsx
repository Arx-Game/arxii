/**
 * CharacterCreationPage Integration Tests
 *
 * Tests for the main character creation page, including:
 * - Initial loading states
 * - Draft creation flow
 * - Stage navigation
 * - Permission checks
 */

import { screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { CharacterCreationPage } from '../CharacterCreationPage';
import {
  mockEmptyDraft,
  mockDraftWithArea,
  mockCompleteDraft,
  mockStartingAreas,
} from './fixtures';
import {
  mockPlayerAccount,
  mockStaffAccount,
  mockRestrictedAccount,
  mockCanCreateYes,
  mockCanCreateNo,
} from './mocks';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedCharacterCreationQueries,
} from './testUtils';

// Mock the API module
vi.mock('../api', () => ({
  canCreateCharacter: vi.fn(),
  getDraft: vi.fn(),
  createDraft: vi.fn(),
  updateDraft: vi.fn(),
  deleteDraft: vi.fn(),
  getStartingAreas: vi.fn(),
  getSpecies: vi.fn(),
  getFamilies: vi.fn(),
  submitDraft: vi.fn(),
  addToRoster: vi.fn(),
}));

describe('CharacterCreationPage', () => {
  describe('Loading State', () => {
    it('shows loading spinner initially', () => {
      const queryClient = createTestQueryClient();
      // Don't seed data - queries will be in loading state

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      expect(document.querySelector('.animate-spin')).toBeInTheDocument();
    });
  });

  describe('Cannot Create Character', () => {
    it('shows error message when user cannot create characters', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateNo,
        draft: null,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockRestrictedAccount,
      });

      await waitFor(() => {
        expect(screen.getByText('Cannot Create Character')).toBeInTheDocument();
      });

      expect(
        screen.getByText(/you have reached the maximum number of characters/i)
      ).toBeInTheDocument();
    });

    it('shows return home button when cannot create', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateNo,
        draft: null,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockRestrictedAccount,
      });

      await waitFor(() => {
        expect(screen.getByRole('link', { name: /return home/i })).toBeInTheDocument();
      });
    });
  });

  describe('No Draft - Start Screen', () => {
    it('shows start character creation button when no draft exists', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: null,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /start character creation/i })
        ).toBeInTheDocument();
      });
    });

    it('displays welcome message', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: null,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(screen.getByText('Create a New Character')).toBeInTheDocument();
      });

      expect(screen.getByText(/begin your journey by creating a character/i)).toBeInTheDocument();
    });
  });

  describe('Existing Draft - Stage Display', () => {
    it('shows stage stepper when draft exists', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockEmptyDraft,
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(screen.getByText('Character Creation')).toBeInTheDocument();
      });

      // Stage stepper should show stages
      expect(screen.getByText('Origin')).toBeInTheDocument();
    });

    it('renders the current stage component', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockEmptyDraft,
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        // Origin stage should be displayed (Stage 1)
        expect(screen.getByText('Choose Your Origin')).toBeInTheDocument();
      });
    });

    it('shows navigation buttons', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockDraftWithArea,
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument();
      });

      expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
    });

    it('disables Previous button on first stage', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockEmptyDraft, // Stage 1
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        const prevButton = screen.getByRole('button', { name: /previous/i });
        expect(prevButton).toBeDisabled();
      });
    });

    it('disables Next button on last stage', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockCompleteDraft, // Stage 8 (Review)
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        const nextButton = screen.getByRole('button', { name: /next/i });
        expect(nextButton).toBeDisabled();
      });
    });
  });

  describe('Staff Features', () => {
    it('staff can see all stages and features', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockCompleteDraft,
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockStaffAccount,
      });

      await waitFor(() => {
        // Staff should see the Review stage with Add to Roster button
        expect(screen.getByText('Review & Submit')).toBeInTheDocument();
      });

      // Staff-only button should be visible
      expect(screen.getByRole('button', { name: /add to roster/i })).toBeInTheDocument();
    });
  });

  describe('Page Header', () => {
    it('displays page title', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockDraftWithArea,
        startingAreas: mockStartingAreas,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(screen.getByText('Character Creation')).toBeInTheDocument();
      });
    });
  });
});
