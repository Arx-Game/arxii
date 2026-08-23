/**
 * Targeted test: VoteButton visibility gating on journal entry rows (#3302).
 *
 * Mirrors `scenes/components/__tests__/PoseUnit.voteButton.test.tsx`, using the same
 * gating shape (VoteButton has no self-guard of its own; the backend rejects
 * self-votes, so this gate is UX only), applied to `JournalsPage`'s public
 * feed rows instead of poses. `entry.author` is a CharacterSheet id, so the
 * gate compares it against the viewer's roster `character_id`s (all owned
 * characters, matching the account-level self-vote check in
 * `services/voting.py`'s `get_author_account_for_target`) rather than the
 * persona-id comparison PoseUnit uses.
 *
 * Scope: gating only. VoteButton's own budget-disabled behavior is its own
 * concern and isn't retested here.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { JournalEntrySummary, PaginatedJournalEntries } from '../api';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// Viewer roster resolution, mirroring PoseUnit.voteButton.test.tsx's idiom.
// character_id 42 is "owned" by the viewer for these tests.
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'ViewerChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 7,
        active_persona_id: 7,
      },
    ],
  })),
}));

// Vote hooks, mocked so VoteButton renders without hitting the network.
const mockCastVote = vi.fn();
const mockRemoveVote = vi.fn();
vi.mock('@/progression/voteQueries', () => ({
  useMyVotesQuery: vi.fn(() => ({ data: [] })),
  useVoteBudgetQuery: vi.fn(() => ({
    data: { base_votes: 5, scene_bonus_votes: 0, votes_spent: 0, votes_remaining: 5 },
  })),
  useCastVoteMutation: vi.fn(() => ({ mutate: mockCastVote, isPending: false })),
  useRemoveVoteMutation: vi.fn(() => ({ mutate: mockRemoveVote, isPending: false })),
}));

const mockUseJournalEntries = vi.fn();
const mockUseMyJournalEntries = vi.fn();
const mockUseJournalEntry = vi.fn();
const mockUseRespondToJournal = vi.fn();
const mockUseCreateJournalEntry = vi.fn();

vi.mock('../queries', () => ({
  useJournalEntries: () => mockUseJournalEntries(),
  useMyJournalEntries: () => mockUseMyJournalEntries(),
  useJournalEntry: () => mockUseJournalEntry(),
  useRespondToJournal: () => mockUseRespondToJournal(),
  useCreateJournalEntry: () => mockUseCreateJournalEntry(),
  useJournalDisposition: () => ({ data: undefined }),
  useSetJournalDisposition: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { JournalsPage } from '../pages/JournalsPage';

function makeEntry(overrides: Partial<JournalEntrySummary> = {}): JournalEntrySummary {
  return {
    id: 1,
    author: 99,
    author_name: 'Someone Else',
    title: 'A Quiet Evening',
    is_public: true,
    response_type: null,
    parent: null,
    created_at: '2026-01-01T00:00:00Z',
    edited_at: null,
    tags: [],
    response_count: 0,
    ...overrides,
  };
}

function makePage(results: JournalEntrySummary[]): PaginatedJournalEntries {
  return { count: results.length, next: null, previous: null, results };
}

function emptyPage(): PaginatedJournalEntries {
  return makePage([]);
}

function Wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('JournalsPage - VoteButton gating (#3302)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMyJournalEntries.mockReturnValue({ data: emptyPage(), isLoading: false });
    mockUseJournalEntry.mockReturnValue({ data: undefined, isLoading: false });
    mockUseRespondToJournal.mockReturnValue({ mutate: vi.fn(), isPending: false });
    mockUseCreateJournalEntry.mockReturnValue({ mutate: vi.fn(), isPending: false });
  });

  it("renders VoteButton on another character's public entry", () => {
    // author 99 is not the viewer (roster character_id 42).
    const entry = makeEntry({ id: 1, author: 99, is_public: true });
    mockUseJournalEntries.mockReturnValue({ data: makePage([entry]), isLoading: false });

    render(
      <Wrapper>
        <JournalsPage />
      </Wrapper>
    );

    const section = screen.getByTestId('public-journals-section');
    expect(within(section).getByTitle(/vote/i)).toBeInTheDocument();
  });

  it("hides VoteButton on the viewer's own public entry", () => {
    // author 42 matches the mocked viewer's roster character_id.
    const entry = makeEntry({ id: 2, author: 42, is_public: true });
    mockUseJournalEntries.mockReturnValue({ data: makePage([entry]), isLoading: false });

    render(
      <Wrapper>
        <JournalsPage />
      </Wrapper>
    );

    const section = screen.getByTestId('public-journals-section');
    expect(within(section).queryByTitle(/vote/i)).toBeNull();
  });

  it('hides VoteButton on entries in the "My Journal" section (always own)', () => {
    const entry = makeEntry({ id: 3, author: 42, is_public: true });
    mockUseMyJournalEntries.mockReturnValue({ data: makePage([entry]), isLoading: false });
    mockUseJournalEntries.mockReturnValue({ data: emptyPage(), isLoading: false });

    render(
      <Wrapper>
        <JournalsPage />
      </Wrapper>
    );

    const section = screen.getByTestId('my-journal-section');
    expect(within(section).queryByTitle(/vote/i)).toBeNull();
  });
});
