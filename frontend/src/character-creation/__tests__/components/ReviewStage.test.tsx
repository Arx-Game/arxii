/**
 * ReviewStage Component Tests
 *
 * Tests for the final review stage, including validation, submission,
 * and staff-only "Add to Roster" functionality.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ReviewStage } from '../../components/ReviewStage';
import {
  mockCGExplanations,
  mockCompleteDraft,
  mockIncompleteDraft,
  mockUpbringingUnknown,
  createMockDraft,
} from '../fixtures';
import { mockPlayerAccount, mockStaffAccount } from '../mocks';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';
import { Stage } from '../../types';

// Mock the API module
vi.mock('../../api', () => ({
  submitDraftForReview: vi.fn(),
  addToRoster: vi.fn(),
  finalizeDraftForTable: vi.fn(),
  getCGExplanations: vi.fn(),
}));

// ReviewStage now calls useTables() to gate the "Finalize for My Table"
// button (#3268) — mock it so these tests don't hit the network. Individual
// tests override the return value with vi.mocked(...).mockReturnValue(...)
// where the GM-table gating matters.
vi.mock('@/tables/queries', () => ({
  useTables: vi.fn(() => ({ data: { count: 0, next: null, previous: null, results: [] } })),
}));

import { useTables } from '@/tables/queries';
import type { GMTable } from '@/tables/types';

function makeGMTable(overrides: Partial<GMTable> = {}): GMTable {
  return {
    id: 1,
    gm: 10,
    gm_username: 'gmUser',
    name: 'Test Table',
    description: '',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    member_count: 2,
    story_count: 1,
    viewer_role: 'gm',
    ...overrides,
  } as GMTable;
}

describe('ReviewStage', () => {
  const mockOnStageSelect = vi.fn();

  beforeEach(() => {
    mockOnStageSelect.mockClear();
  });

  describe('Character Preview', () => {
    it('displays character full name', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Testchar Valardin')).toBeInTheDocument();
    });

    it('displays homeland', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Arx City')).toBeInTheDocument();
    });

    it('displays heritage type', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Normal Upbringing')).toBeInTheDocument();
    });

    it('displays species', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      // mockCompleteDraft has mockSpeciesElf
      expect(screen.getByText('Elf')).toBeInTheDocument();
    });

    it('displays gender', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Female')).toBeInTheDocument();
    });

    it('displays description when provided', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('A tall figure with piercing eyes.')).toBeInTheDocument();
    });

    it('displays personality when provided', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Bold and adventurous.')).toBeInTheDocument();
    });

    it('displays background when provided', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(
        screen.getByText('Born to humble origins but destined for greatness.')
      ).toBeInTheDocument();
    });

    it('shows Unknown for a none-path Upbringing', () => {
      const queryClient = createTestQueryClient();
      const unknownFamilyDraft = createMockDraft({
        ...mockCompleteDraft,
        family: null,
        selected_origin_template: mockUpbringingUnknown,
        family_path: 'none',
      });

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={unknownFamilyDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      expect(screen.getByText('Unknown')).toBeInTheDocument();
    });
  });

  describe('Validation Summary', () => {
    it('shows incomplete sections warning when stages are incomplete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      expect(screen.getByText('Incomplete Sections')).toBeInTheDocument();
      expect(
        screen.getByText(/please complete these sections before submitting/i)
      ).toBeInTheDocument();
    });

    it('lists incomplete stages with links', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      // Attributes & Skills and Distinctions are incomplete in mockIncompleteDraft
      expect(screen.getByText('Attributes & Skills')).toBeInTheDocument();
      expect(screen.getByText('Distinctions')).toBeInTheDocument();
    });

    it('navigates to incomplete stage when clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      const attributesLink = screen.getByText('Attributes & Skills');
      await user.click(attributesLink);

      expect(mockOnStageSelect).toHaveBeenCalledWith(Stage.ATTRIBUTES);
    });

    it('does not show validation warning when all stages complete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.queryByText('Incomplete Sections')).not.toBeInTheDocument();
    });
  });

  describe('Submit Button - Player', () => {
    it('shows submit button for players', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(screen.getByRole('button', { name: /submit for review/i })).toBeInTheDocument();
    });

    it('submit button is disabled when stages incomplete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      expect(submitButton).toBeDisabled();
    });

    it('submit button is enabled when all stages complete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      expect(submitButton).not.toBeDisabled();
    });

    it('does not show "Add to Roster" button for regular players', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(screen.queryByRole('button', { name: /add to roster/i })).not.toBeInTheDocument();
    });
  });

  describe('Staff-Only Features', () => {
    it('shows "Add to Roster" button for staff', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      expect(screen.getByRole('button', { name: /add to roster/i })).toBeInTheDocument();
    });

    it('staff can see both submit and add-to-roster buttons', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      expect(screen.getByRole('button', { name: /submit for review/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /add to roster/i })).toBeInTheDocument();
    });

    it('"Add to Roster" button is disabled when stages incomplete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={true}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient, account: mockStaffAccount }
      );

      const rosterButton = screen.getByRole('button', { name: /add to roster/i });
      expect(rosterButton).toBeDisabled();
    });

    it('"Add to Roster" button is enabled when all stages complete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      const rosterButton = screen.getByRole('button', { name: /add to roster/i });
      expect(rosterButton).not.toBeDisabled();
    });
  });

  describe('Unspent CG Points Banner', () => {
    it('shows banner when draft has unspent CG points', () => {
      const queryClient = createTestQueryClient();
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });

      renderWithCharacterCreationProviders(
        <ReviewStage draft={draftWithUnspent} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText(/15 unspent CG points/i)).toBeInTheDocument();
      expect(screen.getByText(/30 bonus XP/i)).toBeInTheDocument();
    });

    it('does not show banner when all CG points are spent', () => {
      const queryClient = createTestQueryClient();
      const draftAllSpent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 0,
        cg_points_spent: 100,
      });

      renderWithCharacterCreationProviders(
        <ReviewStage draft={draftAllSpent} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.queryByText(/unspent CG points/i)).not.toBeInTheDocument();
    });
  });

  describe('Submit Confirmation Modal', () => {
    it('shows confirmation modal when submitting with unspent points', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });

      renderWithCharacterCreationProviders(
        <ReviewStage draft={draftWithUnspent} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      await user.click(submitButton);

      // Modal should appear with title and action buttons
      expect(screen.getByRole('heading', { name: /unspent cg points/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /go back/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /submit anyway/i })).toBeInTheDocument();
    });

    it('does not show modal when all points spent', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      const draftAllSpent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 0,
        cg_points_spent: 100,
      });

      renderWithCharacterCreationProviders(
        <ReviewStage draft={draftAllSpent} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      await user.click(submitButton);

      // No modal — direct submit
      expect(screen.queryByRole('button', { name: /submit anyway/i })).not.toBeInTheDocument();
    });

    it('closes modal on Go Back', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });

      renderWithCharacterCreationProviders(
        <ReviewStage draft={draftWithUnspent} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      await user.click(submitButton);

      const goBackButton = screen.getByRole('button', { name: /go back/i });
      await user.click(goBackButton);

      // Modal should close
      expect(screen.queryByRole('button', { name: /submit anyway/i })).not.toBeInTheDocument();
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.explanations(), mockCGExplanations);

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Review & Submit')).toBeInTheDocument();
      expect(
        screen.getByText(/review your character before submitting for approval/i)
      ).toBeInTheDocument();
    });
  });

  describe('Finalize for My Table (#3268)', () => {
    it('does not show the button when the account owns no active GM table', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(
        screen.queryByRole('button', { name: /finalize for my table/i })
      ).not.toBeInTheDocument();
    });

    it('shows the button for a non-staff account that owns an active GM table', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { count: 1, next: null, previous: null, results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(screen.getByRole('button', { name: /finalize for my table/i })).toBeInTheDocument();
    });

    it('is disabled when stages are incomplete (reuses the Submit condition)', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { count: 1, next: null, previous: null, results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(screen.getByRole('button', { name: /finalize for my table/i })).toBeDisabled();
    });

    it('ignores tables where the account is not the GM (viewer_role !== "gm")', () => {
      vi.mocked(useTables).mockReturnValue({
        data: {
          count: 1,
          next: null,
          previous: null,
          results: [makeGMTable({ viewer_role: 'member' })],
        },
      } as unknown as ReturnType<typeof useTables>);
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(
        screen.queryByRole('button', { name: /finalize for my table/i })
      ).not.toBeInTheDocument();
    });

    it('does not show the button for staff even if they own a GM table', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { count: 1, next: null, previous: null, results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      expect(
        screen.queryByRole('button', { name: /finalize for my table/i })
      ).not.toBeInTheDocument();
    });

    it('opens the dialog on click', async () => {
      vi.mocked(useTables).mockReturnValue({
        data: { count: 1, next: null, previous: null, results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      await user.click(screen.getByRole('button', { name: /finalize for my table/i }));

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Story Title *')).toBeInTheDocument();
    });
  });
});
