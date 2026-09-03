/**
 * ReviewStage Component Tests
 *
 * The folio treatment (#3540 Task 6): the plate quotes the player's own
 * writing verbatim, the record lists chosen values as doors back to their
 * chapters, and Submit closes with a reason until every other chapter is
 * written. Post-submission renders the second night plate (design law §1).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ReviewStage } from '../components/ReviewStage';
import { Stage } from '../types';
import {
  createMockDraft,
  mockCGExplanations,
  mockCompleteDraft,
  mockIncompleteDraft,
} from './fixtures';
import { mockPlayerAccount, mockStaffAccount } from './mocks';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedCharacterCreationQueries,
} from './testUtils';

const submit = vi.fn();
vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    useSubmitDraft: () => ({ mutate: submit, isPending: false, isError: false }),
    useAddToRoster: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUnsubmitDraft: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useWithdrawDraft: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useResubmitDraft: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useDraftApplication: () => ({ data: null }),
    // No query data: cgRemaining/conversionRate fall back to the draft prop's
    // own cg_points_remaining, so each test controls it via the draft fixture
    // rather than a fixed hook return (mockCompleteDraft's own remaining is 0,
    // so this changes nothing for the brief's verbatim assertions).
    useDraftCGPoints: () => ({ data: undefined }),
  };
});
vi.mock('@/tables/queries', () => ({
  useTables: vi.fn(() => ({ data: { results: [] } })),
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

function renderReview(
  draft: typeof mockCompleteDraft,
  options: {
    isStaff?: boolean;
    onStageSelect?: (stage: Stage) => void;
    account?: typeof mockPlayerAccount;
  } = {}
) {
  const { isStaff = false, onStageSelect = vi.fn(), account } = options;
  const queryClient = createTestQueryClient();
  seedCharacterCreationQueries(queryClient, { explanations: mockCGExplanations });
  return renderWithCharacterCreationProviders(
    <ReviewStage draft={draft} isStaff={isStaff} onStageSelect={onStageSelect} />,
    { queryClient, account }
  );
}

describe('ReviewStage', () => {
  beforeEach(() => {
    submit.mockClear();
    vi.mocked(useTables).mockReturnValue({
      data: { results: [] },
    } as unknown as ReturnType<typeof useTables>);
  });

  it('quotes the player’s own writing under plain labels and composes nothing', async () => {
    renderReview({
      ...mockCompleteDraft,
      draft_data: {
        ...mockCompleteDraft.draft_data,
        glimpse_story: 'I intend to be a captain.',
        background: 'Third daughter.',
      },
    });
    expect(await screen.findByText('I intend to be a captain.')).toBeInTheDocument();
    expect(screen.getByText('Background')).toHaveClass('written-label');
    expect(screen.queryByText(/quick of hand/i)).toBeNull();
  });

  it('keeps Submit closed beside its reason while a chapter is unwritten', async () => {
    renderReview(mockIncompleteDraft);
    const door = await screen.findByRole('button', { name: /submit for review/i });
    expect(door).toHaveAttribute('aria-disabled', 'true');
    expect(door).toHaveAttribute('aria-describedby', 'door-reason');
    await userEvent.click(door);
    expect(submit).not.toHaveBeenCalled();
  });

  it('submits and closes the record on the night plate', async () => {
    renderReview(mockCompleteDraft);
    await userEvent.click(await screen.findByRole('button', { name: /submit for review/i }));
    expect(submit).toHaveBeenCalledWith({ draftId: mockCompleteDraft.id, submissionNotes: '' });
  });

  it('lists every record value as a door back to its chapter', async () => {
    const onStageSelect = vi.fn();
    renderReview(mockCompleteDraft, { onStageSelect });
    await userEvent.click(
      await screen.findByRole('button', { name: mockCompleteDraft.selected_area!.name })
    );
    expect(onStageSelect).toHaveBeenCalledWith(Stage.ORIGIN);
  });

  it('shows "Orphan / No Family" when the draft has no family and is flagged orphan', () => {
    const orphanDraft = createMockDraft({
      ...mockCompleteDraft,
      family: null,
      draft_data: { ...mockCompleteDraft.draft_data, lineage_is_orphan: true },
    });
    renderReview(orphanDraft);
    expect(screen.getByRole('button', { name: 'Orphan / No Family' })).toBeInTheDocument();
  });

  describe('unspent points ledger line', () => {
    it('shows the ledger line when the draft has unspent CG points', () => {
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });
      renderReview(draftWithUnspent);
      expect(screen.getByText(/15 points remain unspent/i)).toBeInTheDocument();
    });

    it('does not show the ledger line when all CG points are spent', () => {
      const draftAllSpent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 0,
        cg_points_spent: 100,
      });
      renderReview(draftAllSpent);
      expect(screen.queryByText(/points remain unspent/i)).toBeNull();
    });
  });

  describe('unspent points conversion dialog (unchanged behaviour)', () => {
    it('shows the confirmation dialog when submitting with unspent points', async () => {
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });
      renderReview(draftWithUnspent, { account: mockPlayerAccount });
      await userEvent.click(await screen.findByRole('button', { name: /submit for review/i }));
      expect(screen.getByRole('heading', { name: /unspent cg points/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /go back/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /submit anyway/i })).toBeInTheDocument();
    });

    it('does not show the dialog when all points are spent', async () => {
      renderReview(mockCompleteDraft, { account: mockPlayerAccount });
      await userEvent.click(await screen.findByRole('button', { name: /submit for review/i }));
      expect(screen.queryByRole('button', { name: /submit anyway/i })).not.toBeInTheDocument();
    });

    it('closes the dialog on Go Back without submitting', async () => {
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });
      renderReview(draftWithUnspent, { account: mockPlayerAccount });
      await userEvent.click(await screen.findByRole('button', { name: /submit for review/i }));
      await userEvent.click(await screen.findByRole('button', { name: /go back/i }));
      expect(screen.queryByRole('button', { name: /submit anyway/i })).not.toBeInTheDocument();
      expect(submit).not.toHaveBeenCalled();
    });
  });

  describe('staff-only doors', () => {
    it('does not show "Add to Roster" for a regular player', () => {
      renderReview(mockCompleteDraft, { isStaff: false, account: mockPlayerAccount });
      expect(screen.queryByRole('button', { name: /add to roster/i })).not.toBeInTheDocument();
    });

    it('shows "Add to Roster" for staff, disabled while a chapter is unwritten', () => {
      renderReview(mockIncompleteDraft, { isStaff: true, account: mockStaffAccount });
      const rosterDoor = screen.getByRole('button', { name: /add to roster/i });
      expect(rosterDoor).toBeDisabled();
    });

    it('enables "Add to Roster" for staff once every chapter is written', () => {
      renderReview(mockCompleteDraft, { isStaff: true, account: mockStaffAccount });
      const rosterDoor = screen.getByRole('button', { name: /add to roster/i });
      expect(rosterDoor).not.toBeDisabled();
    });
  });

  describe('Finalize for My Table (#3268)', () => {
    it('does not show the door when the account owns no active GM table', () => {
      renderReview(mockCompleteDraft, { isStaff: false, account: mockPlayerAccount });
      expect(
        screen.queryByRole('button', { name: /finalize for my table/i })
      ).not.toBeInTheDocument();
    });

    it('shows the door for a non-staff account that owns an active GM table', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      renderReview(mockCompleteDraft, { isStaff: false, account: mockPlayerAccount });
      expect(screen.getByRole('button', { name: /finalize for my table/i })).toBeInTheDocument();
    });

    it('closes the door while stages are incomplete (reuses the Submit condition)', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      renderReview(mockIncompleteDraft, { isStaff: false, account: mockPlayerAccount });
      expect(screen.getByRole('button', { name: /finalize for my table/i })).toBeDisabled();
    });

    it('ignores tables where the account is not the GM (viewer_role !== "gm")', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { results: [makeGMTable({ viewer_role: 'member' })] },
      } as unknown as ReturnType<typeof useTables>);
      renderReview(mockCompleteDraft, { isStaff: false, account: mockPlayerAccount });
      expect(
        screen.queryByRole('button', { name: /finalize for my table/i })
      ).not.toBeInTheDocument();
    });

    it('does not show the door for staff even if they own a GM table', () => {
      vi.mocked(useTables).mockReturnValue({
        data: { results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      renderReview(mockCompleteDraft, { isStaff: true, account: mockStaffAccount });
      expect(
        screen.queryByRole('button', { name: /finalize for my table/i })
      ).not.toBeInTheDocument();
    });

    it('opens the dialog on click', async () => {
      vi.mocked(useTables).mockReturnValue({
        data: { results: [makeGMTable()] },
      } as unknown as ReturnType<typeof useTables>);
      renderReview(mockCompleteDraft, { isStaff: false, account: mockPlayerAccount });
      await userEvent.click(screen.getByRole('button', { name: /finalize for my table/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Story Title *')).toBeInTheDocument();
    });
  });
});
