/**
 * Character-card drawer (#2156, Task 7) — avatar click opens the clicked
 * bubble's persona in-place over the conversation, with Friend/Whisper quick
 * actions. Identity resolution is PUBLIC-roster-only (never outs a disguise):
 * the persona payload carries no roster/character id, so the card must search
 * by exact name and fall back to "not on the roster" for anything that
 * doesn't match exactly — mirrors the leak-table rule in the task brief.
 */
import { fireEvent, screen } from '@testing-library/react';
import { vi } from 'vitest';
import type { UseQueryResult } from '@tanstack/react-query';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { CharacterCardDrawer } from './CharacterCardDrawer';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { PaginatedResponse } from '@/shared/types';
import type { RosterEntryData } from '@/roster/types';

vi.mock('@/roster/queries', () => ({
  useRosterEntryByNameQuery: vi.fn(),
  useRosterEntryQuery: vi.fn(),
}));
vi.mock('@/friends/queries', () => ({
  useAddFriendMutation: vi.fn(),
}));

import { useRosterEntryByNameQuery, useRosterEntryQuery } from '@/roster/queries';
import { useAddFriendMutation } from '@/friends/queries';

const mockSearchQuery = vi.mocked(useRosterEntryByNameQuery);
const mockEntryQuery = vi.mocked(useRosterEntryQuery);
const mockAddFriend = vi.mocked(useAddFriendMutation);

const PERSONA: PoseUnitAvatarClickPersona = { id: 9, name: 'Alice', thumbnail_url: null };

function emptySearch(isLoading = false): PaginatedResponse<RosterEntryData> | undefined {
  return isLoading ? undefined : { count: 0, next: null, previous: null, results: [] };
}

function matchedEntry(): RosterEntryData {
  return {
    id: 42,
    character: {
      id: 100,
      name: 'Alice',
      background: 'Once upon a time in the Vale.',
      age: 30,
      galleries: [],
    },
    profile_picture: null,
    tenures: [],
    can_apply: false,
    fullname: 'Alice',
    quote: '',
    description: '',
    creation_provenance: 'player',
    creation_provenance_display: 'Player-created',
    created_for_table_name: null,
  };
}

function mockNoSearchResult(isLoading = false) {
  mockSearchQuery.mockReturnValue({
    data: emptySearch(isLoading),
    isLoading,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useRosterEntryByNameQuery>);
}

function mockSearchMatch(entry: RosterEntryData) {
  mockSearchQuery.mockReturnValue({
    data: { count: 1, next: null, previous: null, results: [entry] },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useRosterEntryByNameQuery>);
  mockEntryQuery.mockReturnValue({
    data: entry,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as UseQueryResult<RosterEntryData, Error>);
}

describe('CharacterCardDrawer', () => {
  beforeEach(() => {
    mockAddFriend.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useAddFriendMutation>);
    mockEntryQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as UseQueryResult<RosterEntryData, Error>);
  });

  it('renders the persona name and avatar immediately, before the roster search resolves', () => {
    mockNoSearchResult(true);
    renderWithProviders(
      <CharacterCardDrawer
        persona={PERSONA}
        onClose={vi.fn()}
        viewerEntryId={7}
        onWhisper={vi.fn()}
      />
    );
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('renders nothing (drawer closed) when persona is null', () => {
    mockNoSearchResult(false);
    renderWithProviders(
      <CharacterCardDrawer persona={null} onClose={vi.fn()} viewerEntryId={7} onWhisper={vi.fn()} />
    );
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
  });

  describe('with a public roster match', () => {
    beforeEach(() => {
      mockSearchMatch(matchedEntry());
    });

    it('renders BackgroundSection/StatsSection content, the Full profile link, and FriendButton', () => {
      renderWithProviders(
        <CharacterCardDrawer
          persona={PERSONA}
          onClose={vi.fn()}
          viewerEntryId={7}
          onWhisper={vi.fn()}
        />
      );
      expect(screen.getByText(/once upon a time in the vale/i)).toBeInTheDocument();
      const link = screen.getByRole('link', { name: /full profile/i });
      expect(link).toHaveAttribute('href', '/characters/42');
      expect(screen.getByRole('button', { name: /\+ friend alice/i })).toBeInTheDocument();
    });

    it('fires onWhisper with the persona name and closes the drawer', () => {
      const onWhisper = vi.fn();
      const onClose = vi.fn();
      renderWithProviders(
        <CharacterCardDrawer
          persona={PERSONA}
          onClose={onClose}
          viewerEntryId={7}
          onWhisper={onWhisper}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /whisper/i }));
      expect(onWhisper).toHaveBeenCalledWith('Alice');
      expect(onClose).toHaveBeenCalled();
    });

    it('omits the FriendButton when there is no active viewer character', () => {
      renderWithProviders(
        <CharacterCardDrawer
          persona={PERSONA}
          onClose={vi.fn()}
          viewerEntryId={null}
          onWhisper={vi.fn()}
        />
      );
      expect(screen.queryByRole('button', { name: /\+ friend/i })).not.toBeInTheDocument();
    });
  });

  describe('with no public roster match (disguise / temporary / unlisted persona)', () => {
    beforeEach(() => {
      mockNoSearchResult(false);
    });

    it('renders the not-on-roster copy and no FriendButton or sheet data', () => {
      renderWithProviders(
        <CharacterCardDrawer
          persona={PERSONA}
          onClose={vi.fn()}
          viewerEntryId={7}
          onWhisper={vi.fn()}
        />
      );
      expect(screen.getByText(/this face isn't on the public roster/i)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /\+ friend/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /full profile/i })).not.toBeInTheDocument();
    });
  });

  it('fires onClose when the drawer close control is activated', () => {
    mockNoSearchResult(false);
    const onClose = vi.fn();
    renderWithProviders(
      <CharacterCardDrawer
        persona={PERSONA}
        onClose={onClose}
        viewerEntryId={7}
        onWhisper={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
  });
});
