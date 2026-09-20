/**
 * JournalsPage tests (#3941) — the Reading Room's four screens off one route.
 *
 * `/journals` is the stream; `?writer=<sheetId>` is one writer's journal;
 * `?mine=1` is your own. Everything the page reads is mocked, so these assert
 * the page's own decisions: the visit mark is stamped once and never again,
 * Search is a panel rather than a mode, and the desk carries no help text.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { JournalEntryListFilters, JournalEntrySummary, PaginatedJournalEntries } from '../api';
import { PRIMARY_BUTTON_CLASS, QUIET_BUTTON_CLASS } from '../fieldClasses';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/roster/queries', () => ({ useMyRosterEntriesQuery: () => ({ data: [] }) }));
vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: () => ({ results: [], isFetching: false }),
}));
vi.mock('@/progression/nominationQueries', () => ({
  useMyNominationsQuery: () => ({ data: [] }),
  useNominateMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useWithdrawNominationMutation: () => ({ mutate: vi.fn(), isPending: false }),
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
vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => ({
    entryId: 1,
    name: 'Ilsavet du Verane',
    entry: { id: 1, name: 'Ilsavet du Verane', character_id: 10, active_persona_id: 5 },
  }),
}));

const useJournalEntriesMock = vi.fn();
const useMyJournalEntriesMock = vi.fn();
vi.mock('../queries', () => ({
  useJournalEntries: (filters: unknown, markVisitOnce?: boolean) =>
    useJournalEntriesMock(filters, markVisitOnce),
  useMyJournalEntries: (page: number) => useMyJournalEntriesMock(page),
  useJournalEntry: () => ({ data: undefined }),
  useRespondToJournal: () => ({ mutate: vi.fn(), isPending: false }),
  useEditJournalEntry: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateJournalEntry: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useJournalSettings: () => ({
    data: {
      posthumous_journal_disposition: 'reveal',
      retort_consent: 'rivals',
      posts_this_week: 1,
      rewarded_posts_per_week: 3,
    },
  }),
  usePatchJournalSettings: () => ({ mutate: vi.fn(), isPending: false }),
  journalsKeys: { lists: () => ['journals', 'list'] },
}));

import { JournalsPage } from '../pages/JournalsPage';

function entry(over: Partial<JournalEntrySummary> = {}): JournalEntrySummary {
  return {
    id: 1,
    author: 10,
    author_name: 'Ilsavet du Verane',
    title: 'On the matter of the harbor tolls',
    body: 'The tolls are the harbour and the harbour is the city.',
    kind: 'entry',
    is_public: true,
    response_type: null,
    parent: null,
    created_at: '2026-09-17T10:00:00Z',
    edited_at: null,
    tags: [],
    response_count: 0,
    posthumous_override: 'inherit',
    revealed_at: null,
    is_posthumous: false,
    about: 20,
    about_name: 'Corvin Ashe',
    author_persona_id: 99,
    ic_timestamp: null,
    can_retort: false,
    is_own: false,
    ...over,
  };
}

/** The stream as the reader's FIRST request sees it: a mark from a previous visit. */
function page(results: JournalEntrySummary[]): PaginatedJournalEntries {
  return {
    count: results.length,
    next: null,
    previous: null,
    results,
    since_visit_count: 4,
    visited_at: '2026-09-16T08:00:00Z',
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <JournalsPage />
    </MemoryRouter>
  );
}

describe('JournalsPage (#3941)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // WriterBody asks twice: the main (filtered) cut, and a `page_size: 1` probe for the
    // reverse cut's total. Told apart by `page_size`, so each keeps its own answer.
    // Each answer is built ONCE, outside the implementation, and reused by reference on
    // every call: a fresh object per call would make `query.data` a new reference on
    // every re-render, which defeats WriterBody's `useMemo`/`useEffect` dependency
    // checks (the "About" pills are remembered via a `[fresh]` effect dependency) and
    // free-runs a render loop instead of settling.
    const defaultData = page([entry()]);
    const reverseCountData = { ...page([]), count: 1 };
    useJournalEntriesMock.mockImplementation((filters: JournalEntryListFilters = {}) => {
      if (filters.page_size === 1) {
        return { data: reverseCountData, isLoading: false, isSuccess: true };
      }
      return { data: defaultData, isLoading: false, isSuccess: true };
    });
    useMyJournalEntriesMock.mockReturnValue({
      data: page([entry({ id: 7, title: 'A private page', is_own: true })]),
      isLoading: false,
      isSuccess: true,
    });
  });

  it('renders the stream and asks for the visit mark without keying on it', () => {
    renderAt('/journals');

    expect(screen.getByRole('heading', { name: 'Journals' })).toBeInTheDocument();
    expect(screen.getByText('On the matter of the harbor tolls')).toBeInTheDocument();
    // The stream asks to be marked; the hook decides which single fetch carries it.
    expect(useJournalEntriesMock.mock.calls[0][1]).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    fireEvent.click(screen.getByText('Post mortems'));

    const lastFilters = useJournalEntriesMock.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(lastFilters.post_mortem).toBe(1);
    // `mark_visit` never rides the filters, so it can never be part of the query
    // key: a re-render would otherwise swap the key and refetch, and a background
    // refetch would re-stamp the mark and empty "since your last visit".
    for (const call of useJournalEntriesMock.mock.calls) {
      expect((call[0] as Record<string, unknown>).mark_visit).toBeUndefined();
    }
  });

  it('the Search panel cuts on the visit the first response named', () => {
    renderAt('/journals');

    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    // The count and the moment both come off that first response.
    expect(screen.getByText(/Since your last visit/)).toHaveTextContent('4');

    fireEvent.click(screen.getByText(/Since your last visit/));
    const lastFilters = useJournalEntriesMock.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(lastFilters.since).toBe('2026-09-16T08:00:00Z');
  });

  it('the stream renders each row with the prose the feed already sent', () => {
    renderAt('/journals');

    expect(
      screen.getByText('The tolls are the harbour and the harbour is the city.')
    ).toBeInTheDocument();
  });

  it('toggles the Search panel without leaving the stream', () => {
    renderAt('/journals');

    const search = screen.getByRole('button', { name: 'Search' });
    expect(search).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    fireEvent.click(search);
    expect(search).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('table')).toBeInTheDocument();
    // The stream is still there behind the panel: Search is never a mode. The
    // title is a heading in the stream and a button in the index, so the role
    // is what tells the two apart.
    expect(
      screen.getByRole('heading', { name: 'On the matter of the harbor tolls' })
    ).toBeInTheDocument();

    fireEvent.click(search);
    expect(search).toHaveAttribute('aria-expanded', 'false');
  });

  it('?mine=1 shows your journal header and reads the mine feed', () => {
    renderAt('/journals?mine=1');

    expect(screen.getByText('Your journal')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ilsavet du Verane' })).toBeInTheDocument();
    expect(screen.getByText('Rivals only')).toBeInTheDocument();
    expect(screen.getByText('Anyone')).toBeInTheDocument();
    expect(useMyJournalEntriesMock).toHaveBeenCalledWith(1);
    expect(screen.getByText('A private page')).toBeInTheDocument();
  });

  it("?writer= shows the writer's plate and its three filters, and stands alone", () => {
    renderAt('/journals?writer=10');

    expect(screen.getByRole('heading', { name: 'Ilsavet du Verane' })).toBeInTheDocument();
    expect(screen.getByText('Journal of')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About Corvin Ashe · 1' })).toBeInTheDocument();
    // The reverse pill carries the reverse cut's total, from the `page_size: 1` probe
    // the mock above answers with `count: 1` — matching the demo's "Written about her · 1".
    expect(screen.getByRole('button', { name: 'Written about them · 1' })).toBeInTheDocument();
    expect(useJournalEntriesMock.mock.calls[0][0]).toEqual(expect.objectContaining({ author: 10 }));

    // The plate IS the header here (demo screen 2): no page-level heading, no
    // Search/Write/Your journal row above it.
    expect(screen.queryByRole('heading', { name: 'Journals' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Write' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Your journal' })).not.toBeInTheDocument();
  });

  it('Write and Your journal share the same filled emphasis; Search stays quiet', () => {
    renderAt('/journals');

    expect(screen.getByRole('button', { name: 'Search' }).className).toBe(QUIET_BUTTON_CLASS);
    expect(screen.getByRole('button', { name: 'Write' }).className).toBe(PRIMARY_BUTTON_CLASS);
    expect(screen.getByRole('link', { name: 'Your journal' }).className).toBe(
      `${PRIMARY_BUTTON_CLASS} no-underline`
    );
  });

  it('Write opens the desk, which offers the two journals and no help text', () => {
    renderAt('/journals');

    fireEvent.click(screen.getByRole('button', { name: 'Write' }));

    expect(screen.getByText('White journal · Public')).toBeInTheDocument();
    expect(screen.getByText('Black journal · Private')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Post entry' })).toBeInTheDocument();
    expect(screen.getByText(/rewarded entries left this week/)).toHaveTextContent(
      '2 of 3 rewarded entries left this week'
    );
    expect(screen.queryByText(/Read by anyone/)).toBeNull();
    expect(screen.queryByText(/visible only to you/i)).toBeNull();
  });
});
