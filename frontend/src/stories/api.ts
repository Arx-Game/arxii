/**
 * Stories API functions
 *
 * Covers the full Phase 1-3 backend surface:
 * - Story / Chapter / Episode / Beat CRUD
 * - Progress models (GROUP / GLOBAL; CHARACTER scope has no ViewSet)
 * - Action endpoints (resolve, mark, contribute, AGM claims, session requests)
 * - Dashboards (my-active, gm-queue, staff-workload)
 *
 * NOTE: /api/stories/{id}/log/ is intentionally omitted — the backend
 * endpoint does not exist yet. A backend action endpoint must be added
 * before Wave 3 can land the log reader UI.
 *
 * Uses apiFetch from @/evennia_replacements/api.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  AggregateBeatContribution,
  ApproveClaimBody,
  AssistantGMClaim,
  Beat,
  BeatCompletion,
  Chapter,
  ChapterCreateBody,
  ChapterList,
  ContributeBeatBody,
  CreateEventBody,
  Episode,
  EpisodeCreateBody,
  EpisodeList,
  EpisodeResolution,
  GlobalStoryProgress,
  GMQueueResponse,
  GroupStoryProgress,
  MarkBeatBody,
  MyActiveStoriesResponse,
  PaginatedResponse,
  RejectClaimBody,
  RequestClaimBody,
  ResolveEpisodeBody,
  SessionRequest,
  StaffWorkloadResponse,
  Story,
  StoryCreateBody,
  StoryList,
  StoryLogResponse,
} from './types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

// ---------------------------------------------------------------------------
// Dashboard endpoints (APIViews — not paginated)
// ---------------------------------------------------------------------------

export async function getMyActiveStories(): Promise<MyActiveStoriesResponse> {
  const res = await apiFetch('/api/stories/my-active/');
  if (!res.ok) throw new Error('Failed to load active stories');
  return res.json() as Promise<MyActiveStoriesResponse>;
}

export async function getGMQueue(): Promise<GMQueueResponse> {
  const res = await apiFetch('/api/stories/gm-queue/');
  if (!res.ok) {
    const err = new Error('Failed to load GM queue') as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<GMQueueResponse>;
}

export async function getStaffWorkload(): Promise<StaffWorkloadResponse> {
  const res = await apiFetch('/api/stories/staff-workload/');
  if (!res.ok) throw new Error('Failed to load staff workload');
  return res.json() as Promise<StaffWorkloadResponse>;
}

// ---------------------------------------------------------------------------
// Story reads and CRUD
// ---------------------------------------------------------------------------

export interface ListStoriesParams {
  status?: string;
  scope?: string;
  privacy?: string;
  search?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export async function listStories(
  params?: ListStoriesParams
): Promise<PaginatedResponse<StoryList>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/stories/${qs}`);
  if (!res.ok) throw new Error('Failed to load stories');
  return res.json() as Promise<PaginatedResponse<StoryList>>;
}

export async function getStory(id: number): Promise<Story> {
  const res = await apiFetch(`/api/stories/${id}/`);
  if (!res.ok) throw new Error(`Failed to load story ${id}`);
  return res.json() as Promise<Story>;
}

export async function createStory(data: StoryCreateBody): Promise<Story> {
  const res = await apiFetch('/api/stories/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create story');
  return res.json() as Promise<Story>;
}

export async function updateStory(id: number, data: Partial<StoryCreateBody>): Promise<Story> {
  const res = await apiFetch(`/api/stories/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update story ${id}`);
  return res.json() as Promise<Story>;
}

export async function deleteStory(id: number): Promise<void> {
  const res = await apiFetch(`/api/stories/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete story ${id}`);
}

// ---------------------------------------------------------------------------
// Chapter reads and CRUD
// ---------------------------------------------------------------------------

export interface ListChaptersParams {
  story?: number;
  is_active?: boolean;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export async function listChapters(
  params?: ListChaptersParams
): Promise<PaginatedResponse<ChapterList>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/chapters/${qs}`);
  if (!res.ok) throw new Error('Failed to load chapters');
  return res.json() as Promise<PaginatedResponse<ChapterList>>;
}

export async function getChapter(id: number): Promise<Chapter> {
  const res = await apiFetch(`/api/chapters/${id}/`);
  if (!res.ok) throw new Error(`Failed to load chapter ${id}`);
  return res.json() as Promise<Chapter>;
}

export async function createChapter(data: ChapterCreateBody): Promise<Chapter> {
  const res = await apiFetch('/api/chapters/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create chapter');
  return res.json() as Promise<Chapter>;
}

export async function updateChapter(
  id: number,
  data: Partial<ChapterCreateBody>
): Promise<Chapter> {
  const res = await apiFetch(`/api/chapters/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update chapter ${id}`);
  return res.json() as Promise<Chapter>;
}

export async function deleteChapter(id: number): Promise<void> {
  const res = await apiFetch(`/api/chapters/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete chapter ${id}`);
}

// ---------------------------------------------------------------------------
// Episode reads and CRUD
// ---------------------------------------------------------------------------

export interface ListEpisodesParams {
  chapter?: number;
  story?: number;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export async function listEpisodes(
  params?: ListEpisodesParams
): Promise<PaginatedResponse<EpisodeList>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/episodes/${qs}`);
  if (!res.ok) throw new Error('Failed to load episodes');
  return res.json() as Promise<PaginatedResponse<EpisodeList>>;
}

export async function getEpisode(id: number): Promise<Episode> {
  const res = await apiFetch(`/api/episodes/${id}/`);
  if (!res.ok) throw new Error(`Failed to load episode ${id}`);
  return res.json() as Promise<Episode>;
}

export async function createEpisode(data: EpisodeCreateBody): Promise<Episode> {
  const res = await apiFetch('/api/episodes/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create episode');
  return res.json() as Promise<Episode>;
}

export async function updateEpisode(
  id: number,
  data: Partial<EpisodeCreateBody>
): Promise<Episode> {
  const res = await apiFetch(`/api/episodes/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update episode ${id}`);
  return res.json() as Promise<Episode>;
}

export async function deleteEpisode(id: number): Promise<void> {
  const res = await apiFetch(`/api/episodes/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete episode ${id}`);
}

// ---------------------------------------------------------------------------
// Beat reads and CRUD
// ---------------------------------------------------------------------------

export interface ListBeatsParams {
  episode?: number;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export async function listBeats(params?: ListBeatsParams): Promise<PaginatedResponse<Beat>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/beats/${qs}`);
  if (!res.ok) throw new Error('Failed to load beats');
  return res.json() as Promise<PaginatedResponse<Beat>>;
}

export async function getBeat(id: number): Promise<Beat> {
  const res = await apiFetch(`/api/beats/${id}/`);
  if (!res.ok) throw new Error(`Failed to load beat ${id}`);
  return res.json() as Promise<Beat>;
}

export async function createBeat(data: Partial<Beat>): Promise<Beat> {
  const res = await apiFetch('/api/beats/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create beat');
  return res.json() as Promise<Beat>;
}

export async function updateBeat(id: number, data: Partial<Beat>): Promise<Beat> {
  const res = await apiFetch(`/api/beats/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update beat ${id}`);
  return res.json() as Promise<Beat>;
}

export async function deleteBeat(id: number): Promise<void> {
  const res = await apiFetch(`/api/beats/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete beat ${id}`);
}

// ---------------------------------------------------------------------------
// Progress reads (GROUP and GLOBAL; CHARACTER scope has no ViewSet)
// ---------------------------------------------------------------------------

export interface ListGroupProgressParams {
  story?: number;
  gm_table?: number;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}

export async function listGroupStoryProgress(
  params?: ListGroupProgressParams
): Promise<PaginatedResponse<GroupStoryProgress>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/group-story-progress/${qs}`);
  if (!res.ok) throw new Error('Failed to load group story progress');
  return res.json() as Promise<PaginatedResponse<GroupStoryProgress>>;
}

export async function listGlobalStoryProgress(params?: {
  story?: number;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<GlobalStoryProgress>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/global-story-progress/${qs}`);
  if (!res.ok) throw new Error('Failed to load global story progress');
  return res.json() as Promise<PaginatedResponse<GlobalStoryProgress>>;
}

// ---------------------------------------------------------------------------
// Aggregate beat contributions
// ---------------------------------------------------------------------------

export interface ListContributionsParams {
  beat?: number;
  character_sheet?: number;
  page?: number;
  page_size?: number;
}

export async function listAggregateBeatContributions(
  params?: ListContributionsParams
): Promise<PaginatedResponse<AggregateBeatContribution>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/aggregate-beat-contributions/${qs}`);
  if (!res.ok) throw new Error('Failed to load beat contributions');
  return res.json() as Promise<PaginatedResponse<AggregateBeatContribution>>;
}

// ---------------------------------------------------------------------------
// Assistant GM claims
// ---------------------------------------------------------------------------

export interface ListClaimsParams {
  status?: string;
  beat?: number;
  page?: number;
  page_size?: number;
}

export async function listAssistantGMClaims(
  params?: ListClaimsParams
): Promise<PaginatedResponse<AssistantGMClaim>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/assistant-gm-claims/${qs}`);
  if (!res.ok) throw new Error('Failed to load AGM claims');
  return res.json() as Promise<PaginatedResponse<AssistantGMClaim>>;
}

export async function getAssistantGMClaim(id: number): Promise<AssistantGMClaim> {
  const res = await apiFetch(`/api/assistant-gm-claims/${id}/`);
  if (!res.ok) throw new Error(`Failed to load AGM claim ${id}`);
  return res.json() as Promise<AssistantGMClaim>;
}

// ---------------------------------------------------------------------------
// Session requests
// ---------------------------------------------------------------------------

export interface ListSessionRequestsParams {
  status?: string;
  assigned_gm?: number;
  episode?: number;
  page?: number;
  page_size?: number;
}

export async function listSessionRequests(
  params?: ListSessionRequestsParams
): Promise<PaginatedResponse<SessionRequest>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/session-requests/${qs}`);
  if (!res.ok) throw new Error('Failed to load session requests');
  return res.json() as Promise<PaginatedResponse<SessionRequest>>;
}

export async function getSessionRequest(id: number): Promise<SessionRequest> {
  const res = await apiFetch(`/api/session-requests/${id}/`);
  if (!res.ok) throw new Error(`Failed to load session request ${id}`);
  return res.json() as Promise<SessionRequest>;
}

// ---------------------------------------------------------------------------
// Action endpoints
// ---------------------------------------------------------------------------

/**
 * POST /api/episodes/{id}/resolve/
 * Returns 201 EpisodeResolution on success.
 */
export async function resolveEpisode(
  episodeId: number,
  body: ResolveEpisodeBody
): Promise<EpisodeResolution> {
  const res = await apiFetch(`/api/episodes/${episodeId}/resolve/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to resolve episode');
  return res.json() as Promise<EpisodeResolution>;
}

/**
 * POST /api/beats/{id}/mark/
 * Returns 201 BeatCompletion on success.
 */
export async function markBeat(beatId: number, body: MarkBeatBody): Promise<BeatCompletion> {
  const res = await apiFetch(`/api/beats/${beatId}/mark/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to mark beat');
  return res.json() as Promise<BeatCompletion>;
}

/**
 * POST /api/beats/{id}/contribute/
 * Returns 201 AggregateBeatContribution on success.
 */
export async function contributeToBeat(
  beatId: number,
  body: ContributeBeatBody
): Promise<AggregateBeatContribution> {
  const res = await apiFetch(`/api/beats/${beatId}/contribute/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to contribute to beat');
  return res.json() as Promise<AggregateBeatContribution>;
}

/**
 * POST /api/assistant-gm-claims/request/
 * Returns 201 AssistantGMClaim on success.
 */
export async function requestClaim(body: RequestClaimBody): Promise<AssistantGMClaim> {
  const res = await apiFetch('/api/assistant-gm-claims/request/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to request AGM claim');
  return res.json() as Promise<AssistantGMClaim>;
}

/**
 * POST /api/assistant-gm-claims/{id}/approve/
 * Returns 200 updated AssistantGMClaim on success.
 */
export async function approveClaim(
  claimId: number,
  body?: ApproveClaimBody
): Promise<AssistantGMClaim> {
  const res = await apiFetch(`/api/assistant-gm-claims/${claimId}/approve/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error('Failed to approve AGM claim');
  return res.json() as Promise<AssistantGMClaim>;
}

/**
 * POST /api/assistant-gm-claims/{id}/reject/
 * Returns 200 updated AssistantGMClaim on success.
 */
export async function rejectClaim(
  claimId: number,
  body?: RejectClaimBody
): Promise<AssistantGMClaim> {
  const res = await apiFetch(`/api/assistant-gm-claims/${claimId}/reject/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error('Failed to reject AGM claim');
  return res.json() as Promise<AssistantGMClaim>;
}

/**
 * POST /api/assistant-gm-claims/{id}/cancel/
 * Returns 200 updated AssistantGMClaim on success.
 */
export async function cancelClaim(claimId: number): Promise<AssistantGMClaim> {
  const res = await apiFetch(`/api/assistant-gm-claims/${claimId}/cancel/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to cancel AGM claim');
  return res.json() as Promise<AssistantGMClaim>;
}

/**
 * POST /api/assistant-gm-claims/{id}/complete/
 * Returns 200 updated AssistantGMClaim on success.
 */
export async function completeClaim(claimId: number): Promise<AssistantGMClaim> {
  const res = await apiFetch(`/api/assistant-gm-claims/${claimId}/complete/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to complete AGM claim');
  return res.json() as Promise<AssistantGMClaim>;
}

/**
 * POST /api/session-requests/{id}/create-event/
 * Returns 201 updated SessionRequest on success (with event FK populated).
 */
export async function createEventFromSessionRequest(
  requestId: number,
  body: CreateEventBody
): Promise<SessionRequest> {
  const res = await apiFetch(`/api/session-requests/${requestId}/create-event/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to create event from session request');
  return res.json() as Promise<SessionRequest>;
}

/**
 * POST /api/session-requests/{id}/cancel/
 * Returns 200 updated SessionRequest on success.
 */
export async function cancelSessionRequest(requestId: number): Promise<SessionRequest> {
  const res = await apiFetch(`/api/session-requests/${requestId}/cancel/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to cancel session request');
  return res.json() as Promise<SessionRequest>;
}

/**
 * POST /api/session-requests/{id}/resolve/
 * Returns 200 updated SessionRequest on success.
 */
export async function resolveSessionRequest(requestId: number): Promise<SessionRequest> {
  const res = await apiFetch(`/api/session-requests/${requestId}/resolve/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to resolve session request');
  return res.json() as Promise<SessionRequest>;
}

/**
 * GET /api/stories/{id}/log/
 * Returns visibility-filtered story log entries.
 * The generated type for this endpoint is incorrect (shows StoryDetail);
 * the actual response is { entries: StoryLogEntry[] }.
 */
export async function getStoryLog(storyId: number): Promise<StoryLogResponse> {
  const res = await apiFetch(`/api/stories/${storyId}/log/`);
  if (!res.ok) throw new Error('Failed to load story log');
  return res.json() as Promise<StoryLogResponse>;
}

/**
 * POST /api/stories/expire-overdue-beats/
 * Staff-only trigger. Returns { expired_count: number }.
 */
export async function expireOverdueBeats(): Promise<{ expired_count: number }> {
  const res = await apiFetch('/api/stories/expire-overdue-beats/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to expire overdue beats');
  return res.json() as Promise<{ expired_count: number }>;
}
