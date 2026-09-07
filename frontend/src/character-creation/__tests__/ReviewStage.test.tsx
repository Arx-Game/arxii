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
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { ReviewStage } from '../components/ReviewStage';
import { Stage } from '../types';
import { unreachableClasses } from './components/offers/classGuard';
import {
  createMockDraft,
  mockCGExplanations,
  mockCompleteDraft,
  mockIncompleteDraft,
  mockUpbringingUnknown,
} from './fixtures';
import { mockPlayerAccount, mockStaffAccount } from './mocks';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedCharacterCreationQueries,
} from './testUtils';

let draftDistinctions: DraftDistinctionEntry[] = [];
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
}));

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
    useDraftApplication: vi.fn(() => ({ data: null })),
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
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mockNavigate,
}));

import { useTables } from '@/tables/queries';
import { useDraftApplication } from '../queries';
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
    mockNavigate.mockClear();
    draftDistinctions = [];
    vi.mocked(useTables).mockReturnValue({
      data: { results: [] },
    } as unknown as ReturnType<typeof useTables>);
    vi.mocked(useDraftApplication).mockReturnValue({
      data: null,
    } as unknown as ReturnType<typeof useDraftApplication>);
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

  it('lists the draft distinction entries as a ledger of what you carry (#3675 fix round 3)', () => {
    draftDistinctions = [
      {
        distinction_id: 10,
        distinction_name: 'Keen Senses',
        distinction_slug: 'keen-senses',
        category_slug: 'advantages',
        rank: 2,
        cost: 4,
        notes: '',
        offer_ids: [201],
        sources: ['Wonder'],
        arrivals: ['choice'],
      },
      {
        distinction_id: 11,
        distinction_name: 'Orphaned Stances',
        distinction_slug: 'orphaned-stances',
        category_slug: 'drawbacks',
        rank: 1,
        cost: -30,
        notes: '',
        offer_ids: ['state:TEACHERS_GONE'],
        sources: ['No masters remain to teach it.'],
        arrivals: ['carried'],
      },
    ];
    renderReview(mockCompleteDraft);
    expect(screen.getByText('What you carry')).toBeInTheDocument();
    expect(screen.getByText('Keen Senses')).toBeInTheDocument();
    expect(screen.getByText('Rank 2')).toBeInTheDocument();
    expect(screen.getByText('choice')).toBeInTheDocument();
    expect(screen.getByText('Orphaned Stances')).toBeInTheDocument();
    expect(screen.getByText('carried')).toBeInTheDocument();
  });

  it('prints no distinctions ledger when the draft carries none', () => {
    draftDistinctions = [];
    renderReview(mockCompleteDraft);
    expect(screen.queryByText('What you carry')).not.toBeInTheDocument();
  });

  it('emits no class hook that cg.css has no rule for, in the distinctions ledger (#3667 shape)', () => {
    draftDistinctions = [
      {
        distinction_id: 10,
        distinction_name: 'Keen Senses',
        distinction_slug: 'keen-senses',
        category_slug: 'advantages',
        rank: 1,
        cost: 2,
        notes: '',
        offer_ids: [201],
        sources: ['Wonder'],
        arrivals: ['choice'],
      },
    ];
    const queryClient = createTestQueryClient();
    seedCharacterCreationQueries(queryClient, { explanations: mockCGExplanations });
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={vi.fn()} />
      </div>,
      { queryClient }
    );
    // Pre-existing folio-chassis/review classes with no rule reaching the bare
    // element (only a descendant selector) - ChapterLeaf/Marginalia/record-frame
    // primitives this stage already mounts, not created by this task's ledger
    // markup, same escape hatch every other class-guard test uses.
    const styledElsewhere = new Set([
      'review',
      'leaf-body',
      'note-group',
      'plate-name',
      'plate-kicker',
      'written',
      'written-label',
      'quiet-link',
      'record-frame',
      'frame-ledger',
      'unwritten',
    ]);
    expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
  });

  it('shows "Unknown" as the family when the Upbringing takes the none path', () => {
    const unknownFamilyDraft = createMockDraft({
      ...mockCompleteDraft,
      family: null,
      selected_origin_template: mockUpbringingUnknown,
      family_path: 'none',
    });
    renderReview(unknownFamilyDraft);
    expect(screen.getByRole('button', { name: 'Unknown' })).toBeInTheDocument();
  });

  it('shows the chosen Upbringing as a door back to the Lineage chapter', async () => {
    const onStageSelect = vi.fn();
    renderReview(mockCompleteDraft, { onStageSelect });
    await userEvent.click(
      await screen.findByRole('button', {
        name: mockCompleteDraft.selected_origin_template!.name,
      })
    );
    expect(onStageSelect).toHaveBeenCalledWith(Stage.LINEAGE);
  });

  describe('unspent points ledger line', () => {
    it('shows the ledger line when the draft has unspent CG points', () => {
      const draftWithUnspent = createMockDraft({
        ...mockCompleteDraft,
        cg_points_remaining: 15,
        cg_points_spent: 85,
      });
      renderReview(draftWithUnspent);
      expect(screen.getByText(/15 CG points remain unspent/i)).toBeInTheDocument();
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

  describe('approved testament', () => {
    it('keeps a door into the world and navigates to /game on click', async () => {
      vi.mocked(useDraftApplication).mockReturnValue({
        data: { status: 'approved', reviewer_name: null, expires_at: null },
      } as unknown as ReturnType<typeof useDraftApplication>);
      renderReview(mockCompleteDraft);
      const enterWorld = await screen.findByRole('button', { name: /enter the world/i });
      await userEvent.click(enterWorld);
      expect(mockNavigate).toHaveBeenCalledWith('/game');
    });
  });

  describe('application thread link', () => {
    it('shows the revisions message and a thread link when revisions are requested', async () => {
      vi.mocked(useDraftApplication).mockReturnValue({
        data: { status: 'revisions_requested', reviewer_name: null, expires_at: null },
      } as unknown as ReturnType<typeof useDraftApplication>);
      renderReview(mockCompleteDraft);
      expect(
        await screen.findByText(
          'Revisions requested. Check the application thread for staff feedback.'
        )
      ).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /view the application thread/i })).toHaveAttribute(
        'href',
        '/characters/create/application'
      );
    });

    it('shows the thread link on the after-plate while submitted', async () => {
      vi.mocked(useDraftApplication).mockReturnValue({
        data: { status: 'submitted', reviewer_name: null, expires_at: null },
      } as unknown as ReturnType<typeof useDraftApplication>);
      renderReview(mockCompleteDraft);
      expect(
        await screen.findByRole('link', { name: /view the application thread/i })
      ).toHaveAttribute('href', '/characters/create/application');
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
