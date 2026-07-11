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
import { CharacterCardDrawer, resolveWriteupMode } from './CharacterCardDrawer';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { PaginatedResponse } from '@/shared/types';
import type { RosterEntryData } from '@/roster/types';
import type { CharacterRelationshipList } from '@/relationships/api';

vi.mock('@/roster/queries', () => ({
  useRosterEntryByNameQuery: vi.fn(),
  useRosterEntryQuery: vi.fn(),
}));
vi.mock('@/friends/queries', () => ({
  useAddFriendMutation: vi.fn(),
}));
vi.mock('@/relationships/queries', () => ({
  useMyRelationshipToTarget: vi.fn(),
  useRelationshipTracks: vi.fn(),
  useCreateFirstImpression: vi.fn(),
  useCreateDevelopment: vi.fn(),
  useCreateCapstone: vi.fn(),
  useRedistributePoints: vi.fn(),
}));

import { useRosterEntryByNameQuery, useRosterEntryQuery } from '@/roster/queries';
import { useAddFriendMutation } from '@/friends/queries';
import {
  useMyRelationshipToTarget,
  useRelationshipTracks,
  useCreateFirstImpression,
  useCreateDevelopment,
  useCreateCapstone,
  useRedistributePoints,
} from '@/relationships/queries';

const mockSearchQuery = vi.mocked(useRosterEntryByNameQuery);
const mockEntryQuery = vi.mocked(useRosterEntryQuery);
const mockAddFriend = vi.mocked(useAddFriendMutation);
const mockMyRelationship = vi.mocked(useMyRelationshipToTarget);
const mockTracks = vi.mocked(useRelationshipTracks);
const mockCreateFirstImpression = vi.mocked(useCreateFirstImpression);
const mockCreateDevelopment = vi.mocked(useCreateDevelopment);
const mockCreateCapstone = vi.mocked(useCreateCapstone);
const mockRedistributePoints = vi.mocked(useRedistributePoints);

const PERSONA: PoseUnitAvatarClickPersona = { id: 9, name: 'Alice', thumbnail_url: null };

function emptySearch(isLoading = false): PaginatedResponse<RosterEntryData> | undefined {
  return isLoading ? undefined : { count: 0, next: null, previous: null, results: [] };
}

function matchedEntry(tenures: RosterEntryData['tenures'] = []): RosterEntryData {
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
    tenures,
    can_apply: false,
    fullname: 'Alice',
    quote: '',
    description: '',
    creation_provenance: 'player',
    creation_provenance_display: 'Player-created',
    created_for_table_name: null,
  };
}

function liveTenure(): RosterEntryData['tenures'][number] {
  return {
    id: 7,
    player_number: 1,
    start_date: '2026-01-01',
    end_date: null,
    applied_date: '2026-01-01',
    approved_date: '2026-01-01',
    approved_by: null,
    tenure_notes: '',
    photo_folder: '',
    media: [],
  };
}

function endedTenure(): RosterEntryData['tenures'][number] {
  return { ...liveTenure(), id: 8, end_date: '2026-02-01' };
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
    mockMyRelationship.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useMyRelationshipToTarget>);
    mockTracks.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useRelationshipTracks>);
    const mutationStub = {
      mutate: vi.fn(),
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
    };
    mockCreateFirstImpression.mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useCreateFirstImpression>
    );
    mockCreateDevelopment.mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useCreateDevelopment>
    );
    mockCreateCapstone.mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useCreateCapstone>
    );
    mockRedistributePoints.mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useRedistributePoints>
    );
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

  // #2160 Task 4: quick actions.
  it('renders both quick actions when entry+live tenure resolve; hides "Send a letter" with no live tenure', () => {
    mockSearchMatch(matchedEntry([liveTenure()]));
    const { unmount } = renderWithProviders(
      <CharacterCardDrawer
        persona={PERSONA}
        onClose={vi.fn()}
        viewerEntryId={7}
        onWhisper={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /write a journal/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send a letter/i })).toBeInTheDocument();
    unmount();

    mockSearchMatch(matchedEntry([endedTenure()]));
    renderWithProviders(
      <CharacterCardDrawer
        persona={PERSONA}
        onClose={vi.fn()}
        viewerEntryId={7}
        onWhisper={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /write a journal/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send a letter/i })).not.toBeInTheDocument();
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

  describe('resolveWriteupMode (#2159 — "Record an impression" quick action)', () => {
    it('picks development mode when an existing relationship is found, else impression', () => {
      const existing = [
        {
          id: 1,
          source: 7,
          source_name: 'Me',
          target: 100,
          target_name: 'Alice',
          is_active: true,
          is_pending: false,
          is_soul_tether: false,
          soul_tether_role: '',
          absolute_value: 5,
          developed_absolute_value: 2,
          affection: 2,
          updated_at: '2026-01-01T00:00:00Z',
        },
      ] as unknown as CharacterRelationshipList[];
      expect(resolveWriteupMode(existing)).toBe('development');
      expect(resolveWriteupMode([])).toBe('impression');
      expect(resolveWriteupMode(undefined)).toBe('impression');
    });
  });
});
