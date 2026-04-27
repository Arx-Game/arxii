/**
 * Stories Query Hooks Tests
 *
 * Tests for React Query hooks used in the stories feature.
 * Uses the same Vitest + React Query wrapper pattern as narrative tests.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  storiesKeys,
  useApproveClaim,
  useAssistantGMClaims,
  useContributeToBeat,
  useGMQueue,
  useMarkBeat,
  useMyActiveStories,
  useResolveEpisode,
  useStory,
} from '../queries';

// Mock the API module
vi.mock('../api', () => ({
  getMyActiveStories: vi.fn(),
  getGMQueue: vi.fn(),
  getStaffWorkload: vi.fn(),
  getStory: vi.fn(),
  listStories: vi.fn(),
  createStory: vi.fn(),
  updateStory: vi.fn(),
  deleteStory: vi.fn(),
  listChapters: vi.fn(),
  getChapter: vi.fn(),
  createChapter: vi.fn(),
  updateChapter: vi.fn(),
  deleteChapter: vi.fn(),
  listEpisodes: vi.fn(),
  getEpisode: vi.fn(),
  createEpisode: vi.fn(),
  updateEpisode: vi.fn(),
  deleteEpisode: vi.fn(),
  listBeats: vi.fn(),
  getBeat: vi.fn(),
  createBeat: vi.fn(),
  updateBeat: vi.fn(),
  deleteBeat: vi.fn(),
  listGroupStoryProgress: vi.fn(),
  listGlobalStoryProgress: vi.fn(),
  listAggregateBeatContributions: vi.fn(),
  listAssistantGMClaims: vi.fn(),
  getAssistantGMClaim: vi.fn(),
  listSessionRequests: vi.fn(),
  getSessionRequest: vi.fn(),
  resolveEpisode: vi.fn(),
  markBeat: vi.fn(),
  contributeToBeat: vi.fn(),
  requestClaim: vi.fn(),
  approveClaim: vi.fn(),
  rejectClaim: vi.fn(),
  cancelClaim: vi.fn(),
  completeClaim: vi.fn(),
  createEventFromSessionRequest: vi.fn(),
  cancelSessionRequest: vi.fn(),
  resolveSessionRequest: vi.fn(),
  expireOverdueBeats: vi.fn(),
}));

import * as api from '../api';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

const mockMyActiveResponse = {
  character_stories: [
    {
      story_id: 1,
      story_title: 'A tale of two cities',
      scope: 'character' as const,
      current_episode_id: 10,
      current_episode_title: 'The Arrival',
      chapter_title: 'Chapter One',
      status: 'waiting_on_beats',
      status_label: 'Waiting on beats',
      chapter_order: 1,
      episode_order: 2,
      open_session_request_id: null,
      scheduled_event_id: null,
      scheduled_real_time: null,
    },
  ],
  group_stories: [],
  global_stories: [],
};

const mockGMQueueResponse = {
  episodes_ready_to_run: [
    {
      story_id: 5,
      story_title: 'The Siege',
      scope: 'group' as const,
      episode_id: 20,
      episode_title: 'The Final Push',
      progress_type: 'group' as const,
      progress_id: 3,
      eligible_transitions: [{ transition_id: 7, mode: 'auto' as const }],
      open_session_request_id: 12,
    },
  ],
  pending_agm_claims: [],
  assigned_session_requests: [],
};

const mockStory = {
  id: 1,
  title: 'A tale of two cities',
  description: 'A story of revolution.',
  status: 'active' as const,
  privacy: 'private' as const,
  scope: 'character' as const,
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 42,
  chapters_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  completed_at: null,
};

const mockBeatCompletion = {
  id: 99,
  beat: 15,
  character_sheet: 42,
  gm_table: null,
  roster_entry: null,
  outcome: 'success' as const,
  era: null,
  gm_notes: 'Well done.',
  recorded_at: '2026-04-19T12:00:00Z',
};

const mockEpisodeResolution = {
  id: 55,
  episode: 20,
  character_sheet: null,
  gm_table: 3,
  chosen_transition: 7,
  resolved_by: 2,
  era: null,
  gm_notes: 'Great session.',
  resolved_at: '2026-04-19T15:00:00Z',
};

const mockClaim = {
  id: 8,
  beat: 15,
  assistant_gm: 4,
  status: 'requested' as const,
  approved_by: null,
  rejection_note: '',
  framing_note: '',
  requested_at: '2026-04-19T10:00:00Z',
  updated_at: '2026-04-19T10:00:00Z',
};

const mockContribution = {
  id: 77,
  beat: 15,
  character_sheet: 42,
  roster_entry: null,
  points: 10,
  era: null,
  source_note: 'Siege battle participation',
  recorded_at: '2026-04-19T11:00:00Z',
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Stories Query Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // storiesKeys factory
  // -------------------------------------------------------------------------
  describe('storiesKeys', () => {
    it('generates correct query keys', () => {
      expect(storiesKeys.all).toEqual(['stories']);
      expect(storiesKeys.myActive()).toEqual(['stories', 'my-active']);
      expect(storiesKeys.gmQueue()).toEqual(['stories', 'gm-queue']);
      expect(storiesKeys.staffWorkload()).toEqual(['stories', 'staff-workload']);
      expect(storiesKeys.story(1)).toEqual(['stories', 'story', 1]);
      expect(storiesKeys.storyList({ status: 'active' })).toEqual([
        'stories',
        'list',
        { status: 'active' },
      ]);
      expect(storiesKeys.agmClaims({ status: 'requested' })).toEqual([
        'stories',
        'agm-claims',
        { status: 'requested' },
      ]);
    });
  });

  // -------------------------------------------------------------------------
  // useMyActiveStories
  // -------------------------------------------------------------------------
  describe('useMyActiveStories', () => {
    it('returns the expected shape', async () => {
      vi.mocked(api.getMyActiveStories).mockResolvedValue(mockMyActiveResponse);

      const { result } = renderHook(() => useMyActiveStories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockMyActiveResponse);
      expect(result.current.data?.character_stories).toHaveLength(1);
      expect(result.current.data?.character_stories[0].story_title).toBe('A tale of two cities');
    });

    it('enters error state on fetch failure', async () => {
      vi.mocked(api.getMyActiveStories).mockRejectedValue(new Error('Network error'));
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const { result } = renderHook(() => useMyActiveStories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => !result.current.isLoading || result.current.error !== null, {
        timeout: 2000,
      });

      expect(api.getMyActiveStories).toHaveBeenCalledTimes(1);
      consoleSpy.mockRestore();
    });
  });

  // -------------------------------------------------------------------------
  // useGMQueue
  // -------------------------------------------------------------------------
  describe('useGMQueue', () => {
    it('returns episodes ready to run', async () => {
      vi.mocked(api.getGMQueue).mockResolvedValue(mockGMQueueResponse);

      const { result } = renderHook(() => useGMQueue(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.episodes_ready_to_run).toHaveLength(1);
      expect(result.current.data?.episodes_ready_to_run[0].episode_id).toBe(20);
    });
  });

  // -------------------------------------------------------------------------
  // useStory
  // -------------------------------------------------------------------------
  describe('useStory', () => {
    it('fetches a single story by id', async () => {
      vi.mocked(api.getStory).mockResolvedValue(mockStory);

      const { result } = renderHook(() => useStory(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockStory);
      expect(api.getStory).toHaveBeenCalledWith(1);
    });
  });

  // -------------------------------------------------------------------------
  // useResolveEpisode
  // -------------------------------------------------------------------------
  describe('useResolveEpisode', () => {
    it('calls resolveEpisode and invalidates the right keys on success', async () => {
      vi.mocked(api.resolveEpisode).mockResolvedValue(mockEpisodeResolution);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useResolveEpisode(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          episodeId: 20,
          storyId: 5,
          chosen_transition: 7,
          gm_notes: 'Great session.',
        });
      });

      expect(api.resolveEpisode).toHaveBeenCalledWith(20, {
        chosen_transition: 7,
        gm_notes: 'Great session.',
      });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.episode(20) })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.myActive() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.gmQueue() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.storyLog(5) })
      );
    });
  });

  // -------------------------------------------------------------------------
  // useMarkBeat
  // -------------------------------------------------------------------------
  describe('useMarkBeat', () => {
    it('calls markBeat and invalidates beat and dashboards', async () => {
      vi.mocked(api.markBeat).mockResolvedValue(mockBeatCompletion);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useMarkBeat(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          beatId: 15,
          storyId: 3,
          outcome: 'success',
          gm_notes: 'Well done.',
        });
      });

      expect(api.markBeat).toHaveBeenCalledWith(15, {
        outcome: 'success',
        gm_notes: 'Well done.',
      });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.beat(15) })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.gmQueue() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.storyLog(3) })
      );
    });
  });

  // -------------------------------------------------------------------------
  // useContributeToBeat
  // -------------------------------------------------------------------------
  describe('useContributeToBeat', () => {
    it('calls contributeToBeat and invalidates contributions and active stories', async () => {
      vi.mocked(api.contributeToBeat).mockResolvedValue(mockContribution);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useContributeToBeat(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          beatId: 15,
          character_sheet: 42,
          points: 10,
          source_note: 'Siege battle participation',
        });
      });

      expect(api.contributeToBeat).toHaveBeenCalledWith(15, {
        character_sheet: 42,
        points: 10,
        source_note: 'Siege battle participation',
      });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.contributions() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.myActive() })
      );
    });
  });

  // -------------------------------------------------------------------------
  // useApproveClaim
  // -------------------------------------------------------------------------
  describe('useApproveClaim', () => {
    it('calls approveClaim and invalidates claim and gm-queue', async () => {
      const approvedClaim = { ...mockClaim, status: 'approved' as const };
      vi.mocked(api.approveClaim).mockResolvedValue(approvedClaim);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useApproveClaim(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          claimId: 8,
          framing_note: 'The city burns at dawn.',
        });
      });

      expect(api.approveClaim).toHaveBeenCalledWith(8, {
        framing_note: 'The city burns at dawn.',
      });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.agmClaim(8) })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.agmClaims() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.gmQueue() })
      );
    });
  });

  // -------------------------------------------------------------------------
  // useAssistantGMClaims
  // -------------------------------------------------------------------------
  describe('useAssistantGMClaims', () => {
    it('fetches claims with status filter', async () => {
      const mockPaginated = {
        count: 1,
        next: null,
        previous: null,
        results: [mockClaim],
      };
      vi.mocked(api.listAssistantGMClaims).mockResolvedValue(mockPaginated);

      const { result } = renderHook(() => useAssistantGMClaims({ status: 'requested' }), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.results).toHaveLength(1);
      expect(result.current.data?.results[0].status).toBe('requested');
      expect(api.listAssistantGMClaims).toHaveBeenCalledWith({ status: 'requested' });
    });
  });
});
