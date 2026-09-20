/**
 * Targeted test: NominateButton visibility gating on journal rows (#3302,
 * nominations since #3738; rebuilt for the Reading Room, #3941).
 *
 * Mirrors `scenes/components/__tests__/PoseUnit.nominateButton.test.tsx`, using the
 * same gating shape (the button has no self-guard of its own; the backend refuses
 * your own characters, so this gate is UX only), applied to the stream's rows
 * instead of poses.
 *
 * Two things changed with the Reading Room and this test follows both: a row
 * carries its own `is_own` from the backend rather than being matched against the
 * viewer's roster, and the actions — Nominate among them — only exist once the row
 * is OPEN. A collapsed stream shows no buttons at all.
 *
 * Scope: gating only.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { JournalEntrySummary, PaginatedJournalEntries } from '../api';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/roster/queries', () => ({ useMyRosterEntriesQuery: () => ({ data: [] }) }));
vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: () => ({ results: [], isFetching: false }),
}));

// Nomination hooks, mocked so NominateButton renders without hitting the network.
const mockNominate = vi.fn();
const mockWithdraw = vi.fn();
vi.mock('@/progression/nominationQueries', () => ({
  useMyNominationsQuery: vi.fn(() => ({ data: [] })),
  useNominateMutation: vi.fn(() => ({ mutate: mockNominate, isPending: false })),
  useWithdrawNominationMutation: vi.fn(() => ({ mutate: mockWithdraw, isPending: false })),
}));
vi.mock('@/social/queries', () => ({
  useCreateMute: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateBlock: () => ({ mutate: vi.fn(), isPending: false }),
}));

interface StaffState {
  auth: { account: { is_staff: boolean } };
}
vi.mock('@/store/hooks', () => ({
  useAppSelector: (selector: (state: StaffState) => unknown) =>
    selector({ auth: { account: { is_staff: false } } }),
}));
// character_id 42 is the viewer's docked character for these tests.
vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => ({
    entryId: 1,
    name: 'ViewerChar',
    entry: { id: 1, name: 'ViewerChar', character_id: 42, active_persona_id: 7 },
  }),
}));

const mockUseJournalEntries = vi.fn();
const mockUseMyJournalEntries = vi.fn();
vi.mock('../queries', () => ({
  useJournalEntries: () => mockUseJournalEntries(),
  useMyJournalEntries: () => mockUseMyJournalEntries(),
  useJournalEntry: () => ({ data: { body: 'The rain fell softly.', responses: [] } }),
  useRespondToJournal: () => ({ mutate: vi.fn(), isPending: false }),
  useEditJournalEntry: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateJournalEntry: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useJournalSettings: () => ({ data: undefined }),
  usePatchJournalSettings: () => ({ mutate: vi.fn(), isPending: false }),
  journalsKeys: { lists: () => ['journals', 'list'] },
}));

import { JournalsPage } from '../pages/JournalsPage';

function makeEntry(overrides: Partial<JournalEntrySummary> = {}): JournalEntrySummary {
  return {
    id: 1,
    author: 99,
    author_name: 'Someone Else',
    title: 'A Quiet Evening',
    body: 'The rain fell softly on the manor roof.',
    kind: 'entry',
    is_public: true,
    response_type: null,
    parent: null,
    created_at: '2026-01-01T00:00:00Z',
    edited_at: null,
    tags: [],
    response_count: 0,
    posthumous_override: 'inherit',
    revealed_at: null,
    is_posthumous: false,
    about: null,
    about_name: null,
    author_persona_id: 3,
    ic_timestamp: null,
    can_retort: false,
    is_own: false,
    ...overrides,
  };
}

function makePage(results: JournalEntrySummary[]): PaginatedJournalEntries {
  return { count: results.length, next: null, previous: null, results, since_visit_count: 0 };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <JournalsPage />
    </MemoryRouter>
  );
}

/** The actions live behind the fold: open the row before asking what it offers. */
function openRow(title: string) {
  fireEvent.click(screen.getByRole('heading', { name: title }));
}

describe('JournalsPage - NominateButton gating (#3302, #3738, #3941)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMyJournalEntries.mockReturnValue({ data: makePage([]), isLoading: false });
  });

  it("renders NominateButton on another character's opened public entry", () => {
    mockUseJournalEntries.mockReturnValue({
      data: makePage([makeEntry({ id: 1, is_own: false })]),
      isLoading: false,
      isSuccess: true,
    });

    renderAt('/journals');
    expect(screen.queryByTestId('nominate-button')).toBeNull();

    openRow('A Quiet Evening');
    expect(screen.getByTestId('nominate-button')).toBeInTheDocument();
  });

  it("hides NominateButton on the viewer's own opened entry", () => {
    mockUseJournalEntries.mockReturnValue({
      data: makePage([makeEntry({ id: 2, author: 42, author_name: 'ViewerChar', is_own: true })]),
      isLoading: false,
      isSuccess: true,
    });

    renderAt('/journals');
    openRow('A Quiet Evening');

    expect(screen.queryByTestId('nominate-button')).toBeNull();
    // Your own entry offers Edit instead of a way to respond to yourself.
    expect(screen.getByText('Edit')).toBeInTheDocument();
    expect(screen.queryByText('Praise')).toBeNull();
  });

  it('hides NominateButton on a black entry, which can never be nominated', () => {
    mockUseJournalEntries.mockReturnValue({
      data: makePage([makeEntry({ id: 3, is_public: false, is_own: true })]),
      isLoading: false,
      isSuccess: true,
    });

    renderAt('/journals');
    openRow('A Quiet Evening');

    expect(screen.queryByTestId('nominate-button')).toBeNull();
    expect(screen.getByText('Black journal')).toBeInTheDocument();
  });
});
