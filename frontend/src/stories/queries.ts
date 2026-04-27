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
  SendStoryOOCBody,
} from './api';
import type {
  ApproveClaimBody,
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
  RejectClaimBody,
  RequestClaimBody,
  RespondToOfferBody,
  ResolveEpisodeBody,
  StoryCreateBody,
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
      void qc.invalidateQueries({ queryKey: storiesKeys.storyList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
    },
  });
}

export function useUpdateStory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<StoryCreateBody> }) =>
      api.updateStory(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.story(id) });
      void qc.invalidateQueries({ queryKey: storiesKeys.storyList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
    },
  });
}

export function useDeleteStory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteStory(id),
    onSuccess: (_, id) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.storyList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
      // Invalidate the deleted story's cache; the refetch will 404 and clear it.
      void qc.invalidateQueries({ queryKey: storiesKeys.story(id) });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.chapterList({ story }) });
      void qc.invalidateQueries({ queryKey: storiesKeys.story(story) });
    },
  });
}

export function useUpdateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ChapterCreateBody> }) =>
      api.updateChapter(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.chapter(id) });
      void qc.invalidateQueries({ queryKey: storiesKeys.chapterList() });
    },
  });
}

export function useDeleteChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteChapter(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.chapterList() });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.episodeList({ chapter }) });
      void qc.invalidateQueries({ queryKey: storiesKeys.chapter(chapter) });
    },
  });
}

export function useUpdateEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<EpisodeCreateBody> }) =>
      api.updateEpisode(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.episode(id) });
      void qc.invalidateQueries({ queryKey: storiesKeys.episodeList() });
    },
  });
}

export function useDeleteEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteEpisode(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.episodeList() });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.beatList() });
    },
  });
}

export function useUpdateBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof api.updateBeat>[1] }) =>
      api.updateBeat(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.beat(id) });
      void qc.invalidateQueries({ queryKey: storiesKeys.beatList() });
    },
  });
}

export function useDeleteBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteBeat(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.beatList() });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.episode(episodeId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
      void qc.invalidateQueries({ queryKey: storiesKeys.groupProgress() });
      void qc.invalidateQueries({ queryKey: storiesKeys.globalProgress() });
      void qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.beat(beatId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.beatList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
      void qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) });
    },
  });
}

export function useContributeToBeat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ beatId, ...body }: { beatId: number } & ContributeBeatBody) =>
      api.contributeToBeat(beatId, body),
    onSuccess: (_, { beatId }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.beat(beatId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.contributions() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
    },
  });
}

export function useRequestClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RequestClaimBody) => api.requestClaim(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useApproveClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, ...body }: { claimId: number } & ApproveClaimBody) =>
      api.approveClaim(claimId, body),
    onSuccess: (_, { claimId }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useRejectClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, ...body }: { claimId: number } & RejectClaimBody) =>
      api.rejectClaim(claimId, body),
    onSuccess: (_, { claimId }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useCancelClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: number) => api.cancelClaim(claimId),
    onSuccess: (_, claimId) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() });
    },
  });
}

export function useCompleteClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: number) => api.completeClaim(claimId),
    onSuccess: (_, claimId) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaim(claimId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.agmClaims() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useCreateEventFromSessionRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, ...body }: { requestId: number } & CreateEventBody) =>
      api.createEventFromSessionRequest(requestId, body),
    onSuccess: (_, { requestId }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.sessionRequest(requestId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.sessionRequests() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
    },
  });
}

export function useCancelSessionRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requestId: number) => api.cancelSessionRequest(requestId),
    onSuccess: (_, requestId) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.sessionRequest(requestId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.sessionRequests() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useResolveSessionRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requestId: number) => api.resolveSessionRequest(requestId),
    onSuccess: (_, requestId) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.sessionRequest(requestId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.sessionRequests() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
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
      void qc.invalidateQueries({ queryKey: ['narrative'] });
      // Invalidate the story log so the sent notice appears there.
      void qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.beatList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
      void qc.invalidateQueries({ queryKey: storiesKeys.staffWorkload() });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.transitionList() });
    },
  });
}

export function useUpdateTransition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Transition> }) =>
      api.updateTransition(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.transition(id) });
      void qc.invalidateQueries({ queryKey: storiesKeys.transitionList() });
    },
  });
}

export function useDeleteTransition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteTransition(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.transitionList() });
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
      void qc.invalidateQueries({
        queryKey: storiesKeys.progressionRequirements({ episode }),
      });
    },
  });
}

export function useDeleteProgressionRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, episodeId: _episodeId }: { id: number; episodeId: number }) =>
      api.deleteProgressionRequirement(id),
    onSuccess: (_, { episodeId }) => {
      void qc.invalidateQueries({
        queryKey: storiesKeys.progressionRequirements({ episode: episodeId }),
      });
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
      void qc.invalidateQueries({
        queryKey: storiesKeys.transitionRequiredOutcomes({ transition }),
      });
    },
  });
}

export function useDeleteTransitionRequiredOutcome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, transitionId: _transitionId }: { id: number; transitionId: number }) =>
      api.deleteTransitionRequiredOutcome(id),
    onSuccess: (_, { transitionId }) => {
      void qc.invalidateQueries({
        queryKey: storiesKeys.transitionRequiredOutcomes({ transition: transitionId }),
      });
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

export function useDetachStoryFromTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (storyId: number) => api.detachStoryFromTable(storyId),
    onSuccess: (_, storyId) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.storyList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
    },
  });
}

export function useOfferStoryToGM() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storyId, ...body }: { storyId: number } & OfferStoryToGMBody) =>
      api.offerStoryToGM(storyId, body),
    onSuccess: (_, { storyId }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) });
      void qc.invalidateQueries({ queryKey: storiesKeys.storyList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() });
    },
  });
}

export function useAcceptOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, ...body }: { offerId: number } & RespondToOfferBody) =>
      api.acceptOffer(offerId, body),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() });
      void qc.invalidateQueries({ queryKey: storiesKeys.story(updated.story) });
      void qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useDeclineOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, ...body }: { offerId: number } & RespondToOfferBody) =>
      api.declineOffer(offerId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() });
    },
  });
}

export function useWithdrawOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (offerId: number) => api.withdrawOffer(offerId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.storyGMOffers() });
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
      void qc.invalidateQueries({ queryKey: storiesKeys.eraList() });
    },
  });
}

export function useUpdateEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof api.updateEra>[1] }) =>
      api.updateEra(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.era(id) });
      void qc.invalidateQueries({ queryKey: storiesKeys.eraList() });
    },
  });
}

export function useDeleteEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteEra(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storiesKeys.eraList() });
    },
  });
}

export function useAdvanceEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.advanceEra(id),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.eraList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.era(updated.id) });
    },
  });
}

export function useArchiveEra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.archiveEra(id),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: storiesKeys.eraList() });
      void qc.invalidateQueries({ queryKey: storiesKeys.era(updated.id) });
    },
  });
}

// Suppress unused-import lint — Beat is re-exported for consumers
export type { Beat, Era };
