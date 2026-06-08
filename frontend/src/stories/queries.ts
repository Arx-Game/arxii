/**
 * Stories React Query hooks
 *
 * Wraps every api.ts function with React Query hooks.
 * storiesKeys factory provides consistent query keys for cache invalidation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type {
  ListBeatsParams,
  ListChaptersParams,
  ListClaimsParams,
  ListContributionsParams,
  ListErasParams,
  ListEpisodesParams,
  ListGMProfilesParams,
  ListGroupProgressParams,
  ListProgressionRequirementsParams,
  ListSessionRequestsParams,
  ListStoryGMOffersParams,
  ListStoriesParams,
  ListTransitionRequiredOutcomesParams,
  ListTransitionsParams,
  SaveTransitionWithOutcomesBody,
  SendStoryOOCBody,
} from './api';
import type {
  ApproveClaimBody,
  AssignStoryBody,
  Beat,
  BeatOutcome,
  ChapterCreateBody,
  ContributeBeatBody,
  CreateEventBody,
  Era,
  EraCreateBody,
  EpisodeCreateBody,
  EpisodeProgressionRequirement,
  MarkBeatBody,
  OfferStoryToGMBody,
  PromoteEpisodeBody,
  RejectClaimBody,
  RequestClaimBody,
  RespondToOfferBody,
  ResolveEpisodeBody,
  StoryCreateBody,
  StoryNoteRequest,
  Transition,
  TransitionRequiredOutcome,
} from './types';

export type { BeatOutcome };

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const storiesKeys = {
  all: ['stories'] as const,

  // Dashboards
  myActive: () => [...storiesKeys.all, 'my-active'] as const,
  gmQueue: () => [...storiesKeys.all, 'gm-queue'] as const,
  staffWorkload: () => [...storiesKeys.all, 'staff-workload'] as const,

  // Stories
  storyList: (params?: ListStoriesParams) => [...storiesKeys.all, 'list', params] as const,
  story: (id: number) => [...storiesKeys.all, 'story', id] as const,

  // Chapters
  chapterList: (params?: ListChaptersParams) => [...storiesKeys.all, 'chapters', params] as const,
  chapter: (id: number) => [...storiesKeys.all, 'chapter', id] as const,

  // Episodes
  episodeList: (params?: ListEpisodesParams) => [...storiesKeys.all, 'episodes', params] as const,
  episode: (id: number) => [...storiesKeys.all, 'episode', id] as const,

  // Beats
  beatList: (params?: ListBeatsParams) => [...storiesKeys.all, 'beats', params] as const,
  beat: (id: number) => [...storiesKeys.all, 'beat', id] as const,

  // Progress
  groupProgress: (params?: ListGroupProgressParams) =>
    [...storiesKeys.all, 'group-progress', params] as const,
  globalProgress: (params?: { story?: number; is_active?: boolean; page?: number }) =>
    [...storiesKeys.all, 'global-progress', params] as const,

  // Contributions
  contributions: (params?: ListContributionsParams) =>
    [...storiesKeys.all, 'contributions', params] as const,

  // AGM Claims
  agmClaims: (params?: ListClaimsParams) => [...storiesKeys.all, 'agm-claims', params] as const,
  agmClaim: (id: number) => [...storiesKeys.all, 'agm-claim', id] as const,

  // Session requests
  sessionRequests: (params?: ListSessionRequestsParams) =>
    [...storiesKeys.all, 'session-requests', params] as const,
  sessionRequest: (id: number) => [...storiesKeys.all, 'session-request', id] as const,

  // Story log
  storyLog: (id: number) => [...storiesKeys.all, 'story', id, 'log'] as const,

  // Story notes (OOC authorial memory) — keyed by owning story
  storyNotes: (storyId: number) => [...storiesKeys.all, 'story-notes', storyId] as const,

  // Transitions (Wave 9)
  transitionList: (params?: ListTransitionsParams) =>
    [...storiesKeys.all, 'transitions', params] as const,
  transition: (id: number) => [...storiesKeys.all, 'transition', id] as const,

  // EpisodeProgressionRequirements (Wave 9)
  progressionRequirements: (params?: ListProgressionRequirementsParams) =>
    [...storiesKeys.all, 'progression-requirements', params] as const,

  // TransitionRequiredOutcomes (Wave 9)
  transitionRequiredOutcomes: (params?: ListTransitionRequiredOutcomesParams) =>
    [...storiesKeys.all, 'transition-required-outcomes', params] as const,

  // StoryGMOffers (Wave 5)
  storyGMOffers: (params?: ListStoryGMOffersParams) =>
    [...storiesKeys.all, 'story-gm-offers', params] as const,
  storyGMOffer: (id: number) => [...storiesKeys.all, 'story-gm-offer', id] as const,

  // GMProfiles (Wave 5)
  gmProfiles: (params?: ListGMProfilesParams) =>
    [...storiesKeys.all, 'gm-profiles', params] as const,

  // Eras (Wave 6)
  eraList: (params?: ListErasParams) => [...storiesKeys.all, 'eras', params] as const,
  era: (id: number) => [...storiesKeys.all, 'era', id] as const,
};

// ---------------------------------------------------------------------------
// Dashboard hooks
// ---------------------------------------------------------------------------

export function useMyActiveStories() {
  return useQuery({
    queryKey: storiesKeys.myActive(),
    queryFn: api.getMyActiveStories,
    throwOnError: true,
  });
}

export function useGMQueue() {
  return useQuery({
    queryKey: storiesKeys.gmQueue(),
    queryFn: api.getGMQueue,
    throwOnError: true,
  });
}

export function useStaffWorkload() {
  return useQuery({
    queryKey: storiesKeys.staffWorkload(),
    queryFn: api.getStaffWorkload,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Story hooks
// ---------------------------------------------------------------------------

export function useStoryList(params?: ListStoriesParams) {
  return useQuery({
    queryKey: storiesKeys.storyList(params),
    queryFn: () => api.listStories(params),
    throwOnError: true,
  });
}

/**
 * Browse all stories the current user can see (backend-scoped).
 * Optionally filtered by scope. Used by BrowseStoriesPage.
 */
export function useBrowseStories(scope?: string) {
  const params: ListStoriesParams = scope ? { scope } : {};
  return useQuery({
    queryKey: storiesKeys.storyList(params),
    queryFn: () => api.listStories(params),
    throwOnError: true,
  });
}

export function useStory(id: number) {
  return useQuery({
    queryKey: storiesKeys.story(id),
    queryFn: () => api.getStory(id),
    throwOnError: true,
  });
}

export function useCreateStory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: StoryCreateBody) => api.createStory(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.storyList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
    },
  });
}

export function useUpdateStory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<StoryCreateBody> }) =>
      api.updateStory(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.story(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
    },
  });
}

export function useDeleteStory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteStory(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: storiesKeys.storyList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
      // Invalidate the deleted story's cache; the refetch will 404 and clear it.
      qc.invalidateQueries({ queryKey: storiesKeys.story(id) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Chapter hooks
// ---------------------------------------------------------------------------

export function useChapterList(params?: ListChaptersParams) {
  return useQuery({
    queryKey: storiesKeys.chapterList(params),
    queryFn: () => api.listChapters(params),
    throwOnError: true,
  });
}

export function useChapter(id: number) {
  return useQuery({
    queryKey: storiesKeys.chapter(id),
    queryFn: () => api.getChapter(id),
    throwOnError: true,
  });
}

export function useCreateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChapterCreateBody) => api.createChapter(data),
    onSuccess: (_, { story }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.chapterList({ story }) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.story(story) }).catch(() => {});
    },
  });
}

export function useUpdateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ChapterCreateBody> }) =>
      api.updateChapter(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.chapter(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.chapterList() }).catch(() => {});
    },
  });
}

export function useDeleteChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteChapter(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.chapterList() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Episode hooks
// ---------------------------------------------------------------------------

export function useEpisodeList(params?: ListEpisodesParams) {
  return useQuery({
    queryKey: storiesKeys.episodeList(params),
    queryFn: () => api.listEpisodes(params),
    throwOnError: true,
  });
}

export function useEpisode(id: number) {
  return useQuery({
    queryKey: storiesKeys.episode(id),
    queryFn: () => api.getEpisode(id),
    throwOnError: true,
  });
}

export function useCreateEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EpisodeCreateBody) => api.createEpisode(data),
    onSuccess: (_, { chapter }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.episodeList({ chapter }) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.chapter(chapter) }).catch(() => {});
    },
  });
}

export function useUpdateEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<EpisodeCreateBody> }) =>
      api.updateEpisode(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.episode(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.episodeList() }).catch(() => {});
    },
  });
}

export function useDeleteEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteEpisode(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.episodeList() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Beat hooks
// ---------------------------------------------------------------------------

export function useBeatList(params?: ListBeatsParams) {
  return useQuery({
    queryKey: storiesKeys.beatList(params),
    queryFn: () => api.listBeats(params),
    throwOnError: true,
  });
}

export function useBeat(id: number) {
  return useQuery({
    queryKey: storiesKeys.beat(id),
    queryFn: () => api.getBeat(id),
    throwOnError: true,
  });
}

export function useCreateBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof api.createBeat>[0]) => api.createBeat(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.beatList() }).catch(() => {});
    },
  });
}

export function useUpdateBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof api.updateBeat>[1] }) =>
      api.updateBeat(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.beat(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.beatList() }).catch(() => {});
    },
  });
}

export function useDeleteBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteBeat(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.beatList() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Progress hooks
// ---------------------------------------------------------------------------

export function useGroupStoryProgress(params?: ListGroupProgressParams) {
  return useQuery({
    queryKey: storiesKeys.groupProgress(params),
    queryFn: () => api.listGroupStoryProgress(params),
    throwOnError: true,
  });
}

export function useGlobalStoryProgress(params?: {
  story?: number;
  is_active?: boolean;
  page?: number;
}) {
  return useQuery({
    queryKey: storiesKeys.globalProgress(params),
    queryFn: () => api.listGlobalStoryProgress(params),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Aggregate beat contribution hooks
// ---------------------------------------------------------------------------

export function useAggregateBeatContributions(params?: ListContributionsParams) {
  return useQuery({
    queryKey: storiesKeys.contributions(params),
    queryFn: () => api.listAggregateBeatContributions(params),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// AGM claim hooks
// ---------------------------------------------------------------------------

export function useAssistantGMClaims(params?: ListClaimsParams) {
  return useQuery({
    queryKey: storiesKeys.agmClaims(params),
    queryFn: () => api.listAssistantGMClaims(params),
    throwOnError: true,
  });
}

export function useAssistantGMClaim(id: number) {
  return useQuery({
    queryKey: storiesKeys.agmClaim(id),
    queryFn: () => api.getAssistantGMClaim(id),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Session request hooks
// ---------------------------------------------------------------------------

export function useSessionRequests(params?: ListSessionRequestsParams) {
  return useQuery({
    queryKey: storiesKeys.sessionRequests(params),
    queryFn: () => api.listSessionRequests(params),
    throwOnError: true,
  });
}

export function useSessionRequest(id: number) {
  return useQuery({
    queryKey: storiesKeys.sessionRequest(id),
    queryFn: () => api.getSessionRequest(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Action mutation hooks
// ---------------------------------------------------------------------------

export function useResolveEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      episodeId,
      storyId: _storyId,
      ...body
    }: { episodeId: number; storyId: number } & ResolveEpisodeBody) =>
      api.resolveEpisode(episodeId, body),
    onSuccess: (_, { episodeId, storyId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.episode(episodeId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.groupProgress() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.globalProgress() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) }).catch(() => {});
    },
  });
}

export function usePromoteEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      episodeId,
      storyId: _storyId,
      ...body
    }: { episodeId: number; storyId: number } & PromoteEpisodeBody) =>
      api.promoteEpisode(episodeId, body),
    onSuccess: (_, { episodeId, storyId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.episode(episodeId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.episodeList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) }).catch(() => {});
    },
  });
}

export function useMarkBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      beatId,
      storyId: _storyId,
      ...body
    }: { beatId: number; storyId: number } & MarkBeatBody) => api.markBeat(beatId, body),
    onSuccess: (_, { beatId, storyId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.beat(beatId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.beatList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) }).catch(() => {});
    },
  });
}

export function useContributeToBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ beatId, ...body }: { beatId: number } & ContributeBeatBody) =>
      api.contributeToBeat(beatId, body),
    onSuccess: (_, { beatId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.beat(beatId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.contributions() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
    },
  });
}

export function useRequestClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RequestClaimBody) => api.requestClaim(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useApproveClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, ...body }: { claimId: number } & ApproveClaimBody) =>
      api.approveClaim(claimId, body),
    onSuccess: (_, { claimId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useRejectClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, ...body }: { claimId: number } & RejectClaimBody) =>
      api.rejectClaim(claimId, body),
    onSuccess: (_, { claimId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useCancelClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: number) => api.cancelClaim(claimId),
    onSuccess: (_, claimId) => {
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() }).catch(() => {});
    },
  });
}

export function useCompleteClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: number) => api.completeClaim(claimId),
    onSuccess: (_, claimId) => {
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useCreateEventFromSessionRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, ...body }: { requestId: number } & CreateEventBody) =>
      api.createEventFromSessionRequest(requestId, body),
    onSuccess: (_, { requestId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.sessionRequest(requestId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.sessionRequests() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
    },
  });
}

export function useCancelSessionRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requestId: number) => api.cancelSessionRequest(requestId),
    onSuccess: (_, requestId) => {
      qc.invalidateQueries({ queryKey: storiesKeys.sessionRequest(requestId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.sessionRequests() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useResolveSessionRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requestId: number) => api.resolveSessionRequest(requestId),
    onSuccess: (_, requestId) => {
      qc.invalidateQueries({ queryKey: storiesKeys.sessionRequest(requestId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.sessionRequests() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
    },
  });
}

export function useStoryLog(storyId: number) {
  return useQuery({
    queryKey: storiesKeys.storyLog(storyId),
    queryFn: () => api.getStoryLog(storyId),
    enabled: storyId > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Story OOC sender hook (Wave 8)
// ---------------------------------------------------------------------------

export function useSendStoryOOC() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storyId, ...data }: { storyId: number } & SendStoryOOCBody) =>
      api.sendStoryOOC(storyId, data),
    onSuccess: (_, { storyId }) => {
      // Invalidate narrative messages so the recipient inbox refreshes.
      qc.invalidateQueries({ queryKey: ['narrative'] }).catch(() => {});
      // Invalidate the story log so the sent notice appears there.
      qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) }).catch(() => {});
    },
  });
}

export function useExpireOverdueBeats() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.expireOverdueBeats,
    onSuccess: () => {
      // Expire affects beats across all stories/episodes; invalidate beat lists,
      // dashboards, and workload view. Story/chapter/episode detail queries are
      // left untouched — beat expiry doesn't change episode or story structure.
      qc.invalidateQueries({ queryKey: storiesKeys.beatList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.staffWorkload() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// StoryNote hooks (OOC authorial memory)
// ---------------------------------------------------------------------------

export function useStoryNotes(storyId: number) {
  return useQuery({
    queryKey: storiesKeys.storyNotes(storyId),
    queryFn: () => api.listStoryNotes({ story: storyId }),
    enabled: storyId > 0,
    throwOnError: true,
  });
}

export function useCreateStoryNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StoryNoteRequest) => api.createStoryNote(body),
    onSuccess: (_, { story }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.storyNotes(story) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Transition hooks (Wave 9 author editor)
// ---------------------------------------------------------------------------

export function useTransitionList(params?: ListTransitionsParams) {
  return useQuery({
    queryKey: storiesKeys.transitionList(params),
    queryFn: () => api.listTransitions(params),
    throwOnError: true,
  });
}

export function useCreateTransition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof api.createTransition>[0]) => api.createTransition(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.transitionList() }).catch(() => {});
    },
  });
}

export function useUpdateTransition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Transition> }) =>
      api.updateTransition(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.transition(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.transitionList() }).catch(() => {});
    },
  });
}

export function useDeleteTransition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteTransition(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.transitionList() }).catch(() => {});
    },
  });
}

// Wave 13: atomic save-with-outcomes mutation
export function useSaveTransitionWithOutcomes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SaveTransitionWithOutcomesBody) => api.saveTransitionWithOutcomes(body),
    onSuccess: (transition) => {
      qc.invalidateQueries({ queryKey: storiesKeys.transitionList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.transition(transition.id) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// EpisodeProgressionRequirement hooks (Wave 9 author editor)
// ---------------------------------------------------------------------------

export function useProgressionRequirements(params?: ListProgressionRequirementsParams) {
  return useQuery({
    queryKey: storiesKeys.progressionRequirements(params),
    queryFn: () => api.listProgressionRequirements(params),
    enabled: params?.episode !== undefined,
    throwOnError: true,
  });
}

export function useCreateProgressionRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<EpisodeProgressionRequirement, 'id'>) =>
      api.createProgressionRequirement(data),
    onSuccess: (_, { episode }) => {
      qc.invalidateQueries({
        queryKey: storiesKeys.progressionRequirements({ episode }),
      }).catch(() => {});
    },
  });
}

export function useDeleteProgressionRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, episodeId: _episodeId }: { id: number; episodeId: number }) =>
      api.deleteProgressionRequirement(id),
    onSuccess: (_, { episodeId }) => {
      qc.invalidateQueries({
        queryKey: storiesKeys.progressionRequirements({ episode: episodeId }),
      }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// TransitionRequiredOutcome hooks (Wave 9 author editor)
// ---------------------------------------------------------------------------

export function useTransitionRequiredOutcomes(params?: ListTransitionRequiredOutcomesParams) {
  return useQuery({
    queryKey: storiesKeys.transitionRequiredOutcomes(params),
    queryFn: () => api.listTransitionRequiredOutcomes(params),
    enabled: params?.transition !== undefined,
    throwOnError: true,
  });
}

export function useCreateTransitionRequiredOutcome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<TransitionRequiredOutcome, 'id'>) =>
      api.createTransitionRequiredOutcome(data),
    onSuccess: (_, { transition }) => {
      qc.invalidateQueries({
        queryKey: storiesKeys.transitionRequiredOutcomes({ transition }),
      }).catch(() => {});
    },
  });
}

export function useDeleteTransitionRequiredOutcome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, transitionId: _transitionId }: { id: number; transitionId: number }) =>
      api.deleteTransitionRequiredOutcome(id),
    onSuccess: (_, { transitionId }) => {
      qc.invalidateQueries({
        queryKey: storiesKeys.transitionRequiredOutcomes({ transition: transitionId }),
      }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// StoryGMOffer hooks (Wave 5)
// ---------------------------------------------------------------------------

export function useStoryGMOffers(params?: ListStoryGMOffersParams) {
  return useQuery({
    queryKey: storiesKeys.storyGMOffers(params),
    queryFn: () => api.listStoryGMOffers(params),
    throwOnError: true,
  });
}

export function useAssignStory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storyId, ...body }: { storyId: number } & AssignStoryBody) =>
      api.assignStory(storyId, body),
    onSuccess: (_, { storyId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useDetachStoryFromTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (storyId: number) => api.detachStoryFromTable(storyId),
    onSuccess: (_, storyId) => {
      qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() }).catch(() => {});
    },
  });
}

export function useOfferStoryToGM() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storyId, ...body }: { storyId: number } & OfferStoryToGMBody) =>
      api.offerStoryToGM(storyId, body),
    onSuccess: (_, { storyId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() }).catch(() => {});
    },
  });
}

export function useAcceptOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, ...body }: { offerId: number } & RespondToOfferBody) =>
      api.acceptOffer(offerId, body),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.story(updated.story) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() }).catch(() => {});
    },
  });
}

export function useDeclineOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, ...body }: { offerId: number } & RespondToOfferBody) =>
      api.declineOffer(offerId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() }).catch(() => {});
    },
  });
}

export function useWithdrawOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (offerId: number) => api.withdrawOffer(offerId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// GMProfile hooks (Wave 5 — for offer-to-GM picker)
// ---------------------------------------------------------------------------

export function useGMProfiles(params?: ListGMProfilesParams) {
  return useQuery({
    queryKey: storiesKeys.gmProfiles(params),
    queryFn: () => api.listGMProfiles(params),
  });
}

// ---------------------------------------------------------------------------
// Era hooks (Wave 6)
// ---------------------------------------------------------------------------

export function useEras(params?: ListErasParams) {
  return useQuery({
    queryKey: storiesKeys.eraList(params),
    queryFn: () => api.listEras(params),
    throwOnError: true,
  });
}

export function useEra(id: number) {
  return useQuery({
    queryKey: storiesKeys.era(id),
    queryFn: () => api.getEra(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

export function useCreateEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EraCreateBody) => api.createEra(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.eraList() }).catch(() => {});
    },
  });
}

export function useUpdateEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof api.updateEra>[1] }) =>
      api.updateEra(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.era(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.eraList() }).catch(() => {});
    },
  });
}

export function useDeleteEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteEra(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: storiesKeys.eraList() }).catch(() => {});
    },
  });
}

export function useAdvanceEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.advanceEra(id),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: storiesKeys.eraList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.era(updated.id) }).catch(() => {});
    },
  });
}

export function useArchiveEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.archiveEra(id),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: storiesKeys.eraList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: storiesKeys.era(updated.id) }).catch(() => {});
    },
  });
}

// Suppress unused-import lint — Beat is re-exported for consumers
export type { Beat, Era };
