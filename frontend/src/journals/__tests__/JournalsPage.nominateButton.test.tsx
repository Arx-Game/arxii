/**
 * Targeted test: NominateButton visibility gating on journal entry rows (#3302,
 * nominations since #3738).
 *
 * Mirrors `scenes/components/__tests__/PoseUnit.nominateButton.test.tsx`, using the
 * same gating shape (the button has no self-guard of its own; the backend refuses
 * your own characters, so this gate is UX only), applied to `JournalsPage`'s public
 * feed rows instead of poses. `entry.author` is a CharacterSheet id, so the gate
 * compares it against the viewer's roster `character_id`s (all owned characters,
 * matching the account-level self check in `services/nominations.py`) rather than
 * the persona-id comparison PoseUnit uses.
 *
 * Scope: gating only.
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

// Nomination hooks, mocked so NominateButton renders without hitting the network.
const mockNominate = vi.fn();
const mockWithdraw = vi.fn();
vi.mock('@/progression/nominationQueries', () => ({
  useMyNominationsQuery: vi.fn(() => ({ data: [] })),
  useNominateMutation: vi.fn(() => ({ mutate: mockNominate, isPending: false })),
  useWithdrawNominationMutation: vi.fn(() => ({ mutate: mockWithdraw, isPending: false })),
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
    posthumous_override: 'inherit',
    revealed_at: null,
    is_posthumous: false,
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

describe('JournalsPage - NominateButton gating (#3302, #3738)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMyJournalEntries.mockReturnValue({ data: emptyPage(), isLoading: false });
    mockUseJournalEntry.mockReturnValue({ data: undefined, isLoading: false });
    mockUseRespondToJournal.mockReturnValue({ mutate: vi.fn(), isPending: false });
    mockUseCreateJournalEntry.mockReturnValue({ mutate: vi.fn(), isPending: false });
  });

  it("renders NominateButton on another character's public entry", () => {
    // author 99 is not the viewer (roster character_id 42).
    const entry = makeEntry({ id: 1, author: 99, is_public: true });
    mockUseJournalEntries.mockReturnValue({ data: makePage([entry]), isLoading: false });

    render(
      <Wrapper>
        <JournalsPage />
      </Wrapper>
    );

    const section = screen.getByTestId('public-journals-section');
    expect(within(section).getByTitle(/nominate someone else/i)).toBeInTheDocument();
  });

  it("hides NominateButton on the viewer's own public entry", () => {
    // author 42 matches the mocked viewer's roster character_id.
    const entry = makeEntry({ id: 2, author: 42, is_public: true });
    mockUseJournalEntries.mockReturnValue({ data: makePage([entry]), isLoading: false });

    render(
      <Wrapper>
        <JournalsPage />
      </Wrapper>
    );

    const section = screen.getByTestId('public-journals-section');
    expect(within(section).queryByTitle(/nominate/i)).toBeNull();
  });

  it('hides NominateButton on entries in the "My Journal" section (always own)', () => {
    const entry = makeEntry({ id: 3, author: 42, is_public: true });
    mockUseMyJournalEntries.mockReturnValue({ data: makePage([entry]), isLoading: false });
    mockUseJournalEntries.mockReturnValue({ data: emptyPage(), isLoading: false });

    render(
      <Wrapper>
        <JournalsPage />
      </Wrapper>
    );

    const section = screen.getByTestId('my-journal-section');
    expect(within(section).queryByTitle(/nominate/i)).toBeNull();
  });
});
