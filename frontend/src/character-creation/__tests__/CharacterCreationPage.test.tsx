/**
 * CharacterCreationPage Integration Tests
 *
 * Tests for the main character creation page, including:
 * - Initial loading states
 * - Draft creation flow
 * - Stage navigation
 * - Permission checks
 */

import { screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';
import { distinctionKeys } from '@/hooks/useDistinctions';
import { CharacterCreationPage } from '../CharacterCreationPage';
import { Stage } from '../types';
import {
  mockCGExplanations,
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
  seedQueryData,
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
  submitDraftForReview: vi.fn(),
  addToRoster: vi.fn(),
  getCGExplanations: vi.fn(),
  // GiftStage (#2426 Task 10) calls useResonances() unconditionally at the top
  // of its render (for the always-mounted Gift Resonance step), independent
  // of which funnel step is currently open.
  getResonances: vi.fn().mockResolvedValue([]),
  // GlimpseSection (#2427) calls useGlimpseTags() unconditionally as part of
  // the always-mounted Glimpse guided flow.
  getGlimpseTags: vi.fn().mockResolvedValue([]),
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

  describe('No Draft - Arrival Plate', () => {
    it('shows the open-the-record door when no draft exists', async () => {
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
        expect(screen.getByRole('button', { name: /^begin$/i })).toBeInTheDocument();
      });
    });

    it('displays the arrival title with no eyebrow', async () => {
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
          screen.getByText(/creating a character and starting their story/i)
        ).toBeInTheDocument();
      });

      expect(screen.queryByText(/the durance/i)).not.toBeInTheDocument();
    });
  });

  describe('Existing Draft - Stage Display', () => {
    it('shows the contents rail when draft exists', async () => {
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
        expect(
          screen.getByRole('navigation', { name: /character creation stages/i })
        ).toBeInTheDocument();
      });

      // The contents rail lists every chapter. Origin's own record rail
      // (Task 4) also has a row labeled "Origin", so scope to the nav.
      const nav = screen.getByRole('navigation', { name: /character creation stages/i });
      expect(within(nav).getByText('Origin')).toBeInTheDocument();
    });

    it('renders the current stage component', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockEmptyDraft,
        startingAreas: mockStartingAreas,
        explanations: mockCGExplanations,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        // Origin stage should be displayed (Stage 1)
        expect(screen.getByText('Where does the story begin?')).toBeInTheDocument();
      });
    });

    it('shows the page-turn doors on a mid-flow chapter', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        // Stage.GIFT: neither Origin nor Review, so the shell's PageTurn renders
        // (those two chapters own their own page-turn from Task 2 onward).
        draft: { ...mockDraftWithArea, current_stage: Stage.GIFT },
        startingAreas: mockStartingAreas,
        explanations: mockCGExplanations,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^back:/i })).toBeInTheDocument();
      });

      expect(screen.getByRole('button', { name: /^next:/i })).toBeInTheDocument();
    });

    // Origin and Review are the first and last chapters; the shell renders no
    // generic PageTurn for either (each owns its own door, per the brief -
    // Origin/Review get theirs in Task 2). This replaces the old
    // disabled-button-at-the-edges behavior from the stepper/footer design.
    // Origin's own door (Task 4) has no back door (nothing precedes it) and
    // a forward door disabled until a realm is chosen.
    it('renders no page-turn back door on the first chapter (Origin)', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockEmptyDraft, // Stage.ORIGIN
        startingAreas: mockStartingAreas,
        explanations: mockCGExplanations,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(
          screen.getByRole('navigation', { name: /character creation stages/i })
        ).toBeInTheDocument();
      });

      expect(screen.queryByRole('button', { name: /^back:/i })).not.toBeInTheDocument();
      const forwardDoor = screen.getByRole('button', { name: /^next:/i });
      expect(forwardDoor).toHaveAttribute('aria-disabled', 'true');
    });

    it('renders no page-turn forward door on the last chapter (Review)', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockCompleteDraft, // Stage.REVIEW
        startingAreas: mockStartingAreas,
        explanations: mockCGExplanations,
      });

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      await waitFor(() => {
        expect(screen.getByText('Review & Submit')).toBeInTheDocument();
      });

      expect(screen.queryByRole('button', { name: /^next:/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^back:/i })).not.toBeInTheDocument();
    });
  });

  describe('Arrival', () => {
    it('opens on the night plate with one door that creates the draft', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: null,
        explanations: mockCGExplanations,
      });
      renderWithCharacterCreationProviders(<CharacterCreationPage />, { queryClient });
      const plate = await screen.findByRole('region', {
        name: /creating a character and starting their story/i,
      });
      expect(plate).toHaveClass('plate-night');
      expect(screen.getByText(mockCGExplanations.arrival_intro)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^begin$/i })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
    });
  });

  describe('Gift Stage Dispatch (#2426 Task 10)', () => {
    it('renders GiftStage (not the retired MagicStage) for Stage.GIFT', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: { ...mockEmptyDraft, current_stage: Stage.GIFT },
        startingAreas: mockStartingAreas,
        explanations: mockCGExplanations,
      });
      // GlimpseSection (#2427) calls useDraftDistinctions(draft.id) unconditionally
      // for its manual distinction-link fallback — seed it so the test doesn't
      // fire a real (failing) network fetch.
      seedQueryData(queryClient, distinctionKeys.draftDistinctions(mockEmptyDraft.id), []);

      renderWithCharacterCreationProviders(<CharacterCreationPage />, {
        queryClient,
        account: mockPlayerAccount,
      });

      // The funnel's Anima Check step label always renders, independent of
      // any catalog data loading — a reliable signal GiftStage (not the old
      // MagicStage cantrip UI) is what's mounted. Scoped to the funnel's own
      // entry list — the record rail also carries "Tradition" and
      // "Techniques" rows (#3630), so an unscoped query is ambiguous.
      await waitFor(() => {
        expect(screen.getByText('Anima Check')).toBeInTheDocument();
      });
      const funnel = screen.getByRole('list', { name: 'Gift steps' });
      expect(within(funnel).getByText('Tradition')).toBeInTheDocument();
      expect(within(funnel).getByText('Techniques')).toBeInTheDocument();
    });
  });

  describe('Staff Features', () => {
    it('staff can see all stages and features', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, {
        canCreate: mockCanCreateYes,
        draft: mockCompleteDraft,
        startingAreas: mockStartingAreas,
        explanations: mockCGExplanations,
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
    it('displays the chapters-of-your-character contents rail', async () => {
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
        expect(
          screen.getByRole('navigation', { name: /character creation stages/i })
        ).toBeInTheDocument();
      });
    });
  });
});
