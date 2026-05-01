/**
 * Stories TypeScript types
 *
 * Re-exports from frontend/src/generated/api.d.ts with local aliases,
 * plus hand-defined response shapes for the three dashboard APIView
 * endpoints (which spectacular cannot introspect).
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// ViewSet model schemas — from generated types
// ---------------------------------------------------------------------------

// Stories have two serializer shapes: StoryList (lightweight) and StoryDetail (full).
// We export both and alias the detail shape as Story for most usage.
export type StoryList = components['schemas']['StoryList'];
export type StoryDetailBase = components['schemas']['StoryDetail'];

// StoryDetail with primary_table forced to nullable. The generated schema
// types this as `number` (non-null) because spectacular cannot infer
// nullability from a read-only PrimaryKeyRelatedField, but the backing model
// is `null=True` and the API does return null for stories without a table.
export type StoryDetail = Omit<StoryDetailBase, 'primary_table'> & {
  readonly primary_table: number | null;
};
export type Story = StoryDetail;

// Chapters have three shapes: ChapterList, ChapterDetail, ChapterCreate.
export type ChapterList = components['schemas']['ChapterList'];
export type ChapterDetail = components['schemas']['ChapterDetail'];
export type ChapterCreate = components['schemas']['ChapterCreate'];
export type Chapter = ChapterDetail;

// Episodes have three shapes: EpisodeList, EpisodeDetail, EpisodeCreate.
export type EpisodeList = components['schemas']['EpisodeList'];
export type EpisodeDetail = components['schemas']['EpisodeDetail'];
export type EpisodeCreate = components['schemas']['EpisodeCreate'];
export type Episode = EpisodeDetail;

// Beat — single shape with all Phase 2 predicate config fields plus the
// Wave 7 read-context breadcrumb fields (episode_title, chapter_title,
// story_id, story_title). The generated type now correctly includes these
// as readonly non-nullable fields (verified in api.d.ts Beat schema).
//
// Wave 12: can_mark is a server-computed boolean telling the client whether
// the requesting user may POST /beats/{id}/mark/. Added to BeatSerializer
// in Phase 5 Wave 12; not yet in the schema dump — extended here until
// the next schema regeneration.
export type Beat = components['schemas']['Beat'] & {
  /** True when the requesting user may call POST /beats/{id}/mark/. */
  readonly can_mark: boolean;
};

// Progress — CHARACTER scope has no generated type (no ViewSet); only GROUP and GLOBAL do.
export type GroupStoryProgress = components['schemas']['GroupStoryProgress'];
export type GlobalStoryProgress = components['schemas']['GlobalStoryProgress'];

// Aggregate beat contributions, claims, session requests.
export type AggregateBeatContribution = components['schemas']['AggregateBeatContribution'];
export type AssistantGMClaim = components['schemas']['AssistantGMClaim'];
export type SessionRequest = components['schemas']['SessionRequest'];

// EpisodeResolution and BeatCompletion exist as backend models with serializers
// but spectacular doesn't generate them as named schemas — the generated types
// incorrectly show EpisodeDetail / Beat as the response types for the resolve /
// mark actions. We hand-define them to match the actual serializer fields
// (EpisodeResolutionSerializer and BeatCompletionSerializer in serializers.py).
export interface EpisodeResolution {
  id: number;
  episode: number;
  character_sheet: number | null;
  gm_table: number | null;
  chosen_transition: number | null;
  resolved_by: number | null;
  era: number | null;
  gm_notes: string;
  resolved_at: string;
}

export interface BeatCompletion {
  id: number;
  beat: number;
  character_sheet: number | null;
  gm_table: number | null;
  roster_entry: number | null;
  outcome: BeatOutcome;
  era: number | null;
  gm_notes: string;
  recorded_at: string;
}

// ---------------------------------------------------------------------------
// Enum aliases — NonNullable because these are server-side required enums
// ---------------------------------------------------------------------------

export type BeatPredicateType = NonNullable<Beat['predicate_type']>;
export type BeatOutcome = NonNullable<Beat['outcome']>;
export type BeatVisibility = NonNullable<Beat['visibility']>;
export type StoryScope = NonNullable<Story['scope']>;
export type StoryStatus = NonNullable<Story['status']>;
export type StoryPrivacy = NonNullable<Story['privacy']>;
export type AssistantClaimStatus = NonNullable<AssistantGMClaim['status']>;
export type SessionRequestStatus = NonNullable<SessionRequest['status']>;

// ---------------------------------------------------------------------------
// Union for scope-polymorphic helpers
// (CHARACTER scope has no ViewSet; GROUP and GLOBAL do.)
// ---------------------------------------------------------------------------
export type AnyStoryProgress = GroupStoryProgress | GlobalStoryProgress;

// ---------------------------------------------------------------------------
// Paginated response wrappers
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---------------------------------------------------------------------------
// Dashboard response types — hand-defined from views.py
//
// MyActiveStoriesView (_serialize_progress_entry)
// Returns three lists, each entry built from compute_story_status().
// ---------------------------------------------------------------------------

/**
 * One active story entry from GET /api/stories/my-active/.
 * Built by _serialize_progress_entry() in views.py.
 */
export interface MyActiveStoryEntry {
  story_id: number;
  story_title: string;
  scope: StoryScope;
  current_episode_id: number | null;
  current_episode_title: string | null;
  chapter_title: string | null;
  /** StoryEpisodeStatus value e.g. "waiting_on_beats", "ready_to_resolve" */
  status: string;
  /** Human-readable label from StoryEpisodeStatus.label */
  status_label: string;
  chapter_order: number | null;
  episode_order: number | null;
  open_session_request_id: number | null;
  scheduled_event_id: number | null;
  scheduled_real_time: string | null;
}

export interface MyActiveStoriesResponse {
  character_stories: MyActiveStoryEntry[];
  group_stories: MyActiveStoryEntry[];
  global_stories: MyActiveStoryEntry[];
}

// ---------------------------------------------------------------------------
// GMQueueView
// Returns episodes_ready_to_run, pending_agm_claims, assigned_session_requests.
// Built by _build_gm_queue_for_story() in views.py.
// ---------------------------------------------------------------------------

/** One episode ready to run, from GET /api/stories/gm-queue/. */
export interface GMQueueEpisodeEntry {
  story_id: number;
  story_title: string;
  scope: StoryScope;
  episode_id: number;
  episode_title: string;
  progress_type: StoryScope;
  progress_id: number;
  eligible_transitions: Array<{ transition_id: number; mode: TransitionMode }>;
  open_session_request_id: number | null;
}

/** One pending AGM claim summary, from GET /api/stories/gm-queue/. */
export interface GMQueuePendingClaim {
  claim_id: number;
  beat_id: number;
  beat_internal_description: string;
  story_title: string;
  assistant_gm_id: number;
  requested_at: string;
}

/** One assigned session request summary, from GET /api/stories/gm-queue/. */
export interface GMQueueAssignedRequest {
  session_request_id: number;
  episode_id: number;
  episode_title: string;
  story_title: string;
  status: string;
  event_id: number | null;
}

export interface GMQueueResponse {
  episodes_ready_to_run: GMQueueEpisodeEntry[];
  pending_agm_claims: GMQueuePendingClaim[];
  assigned_session_requests: GMQueueAssignedRequest[];
}

// ---------------------------------------------------------------------------
// StaffWorkloadView
// Returns per_gm_queue_depth, stale_stories, stories_at_frontier, counts.
// Built in StaffWorkloadView.get() in views.py.
// ---------------------------------------------------------------------------

export interface PerGMQueueEntry {
  gm_profile_id: number;
  gm_name: string;
  episodes_ready: number;
  pending_claims: number;
}

export interface StaleStoryEntry {
  story_id: number;
  story_title: string;
  last_advanced_at: string;
  days_stale: number;
}

export interface FrontierStoryEntry {
  story_id: number;
  story_title: string;
  scope: StoryScope;
}

export interface StaffWorkloadResponse {
  per_gm_queue_depth: PerGMQueueEntry[];
  stale_stories: StaleStoryEntry[];
  stories_at_frontier: FrontierStoryEntry[];
  pending_agm_claims_count: number;
  open_session_requests_count: number;
  /** Map of scope → story count */
  counts_by_scope: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Action endpoint request shapes (for API functions)
// ---------------------------------------------------------------------------

export interface ResolveEpisodeBody {
  progress_id?: number | null;
  chosen_transition?: number | null;
  gm_notes?: string;
}

export interface MarkBeatBody {
  outcome: BeatOutcome;
  gm_notes?: string;
  progress_id?: number | null;
}

export interface ContributeBeatBody {
  character_sheet: number;
  points: number;
  source_note?: string;
}

export interface RequestClaimBody {
  beat: number;
  framing_note?: string;
}

export interface ApproveClaimBody {
  framing_note?: string;
}

export interface RejectClaimBody {
  note?: string;
}

export interface CreateEventBody {
  name: string;
  scheduled_real_time: string;
  host_persona: number;
  location_id: number;
  description?: string;
  is_public?: boolean;
}

// Transition, EpisodeProgressionRequirement, TransitionRequiredOutcome — Wave 9 author editor
export type Transition = components['schemas']['Transition'];
export type EpisodeProgressionRequirement = components['schemas']['EpisodeProgressionRequirement'];
export type TransitionRequiredOutcome = components['schemas']['TransitionRequiredOutcome'];

// Enum aliases for Wave 9
export type TransitionMode = NonNullable<Transition['mode']>;
export type StoryConnectionType = NonNullable<components['schemas']['ConnectionTypeEnum']>;
export type ReferencedMilestoneType = NonNullable<
  components['schemas']['ReferencedMilestoneTypeEnum']
>;

export interface StoryCreateBody {
  title: string;
  description: string;
  privacy?: StoryPrivacy;
  scope?: StoryScope;
}

export interface ChapterCreateBody {
  story: number;
  title: string;
  description?: string;
  order?: number;
  is_active?: boolean;
}

export interface EpisodeCreateBody {
  chapter: number;
  title: string;
  description?: string;
  order?: number;
}

// ---------------------------------------------------------------------------
// Beat write-side body types — omit read-only server-derived fields.
//
// Phase 4 used Partial<Beat> for createBeat/updateBeat payloads; Beat
// includes read-only fields (id, episode_title, chapter_title, story_id,
// story_title, created_at, updated_at, can_mark) that must not be sent on
// write requests. These explicit types surface intent and prevent callers
// from accidentally including server-derived data.
// ---------------------------------------------------------------------------

export interface BeatCreateBody {
  episode: number;
  predicate_type?: BeatPredicateType;
  visibility?: BeatVisibility;
  internal_description: string;
  player_hint?: string;
  player_resolution_text?: string;
  order?: number;
  agm_eligible?: boolean;
  deadline?: string | null;

  // Predicate-type-specific config (exactly one set applies per predicate_type):
  required_level?: number | null; // CHARACTER_LEVEL_AT_LEAST
  required_achievement?: number | null; // ACHIEVEMENT_HELD
  required_condition_template?: number | null; // CONDITION_HELD
  required_codex_entry?: number | null; // CODEX_ENTRY_UNLOCKED
  referenced_story?: number | null; // STORY_AT_MILESTONE
  referenced_milestone_type?: ReferencedMilestoneType; // STORY_AT_MILESTONE
  referenced_chapter?: number | null; // STORY_AT_MILESTONE/chapter_reached
  referenced_episode?: number | null; // STORY_AT_MILESTONE/episode_reached
  required_points?: number | null; // AGGREGATE_THRESHOLD
}

export type BeatUpdateBody = Partial<BeatCreateBody>;

// ---------------------------------------------------------------------------
// Story log types — hand-defined from StoryLogSerializer in serializers.py.
// The generated type for stories_log_retrieve incorrectly returns StoryDetail;
// the actual response is { entries: StoryLogEntry[] }.
// ---------------------------------------------------------------------------

export interface StoryLogBeatEntry {
  entry_type: 'beat_completion';
  beat_id: number;
  episode_id: number;
  recorded_at: string;
  outcome: BeatOutcome;
  visibility: BeatVisibility;
  player_hint: string | null;
  player_resolution_text: string | null;
  /** Non-null only for lead GM / staff viewers. */
  internal_description: string | null;
  gm_notes: string | null;
}

export interface StoryLogEpisodeEntry {
  entry_type: 'episode_resolution';
  episode_id: number;
  episode_title: string;
  resolved_at: string;
  transition_id: number | null;
  target_episode_id: number | null;
  target_episode_title: string | null;
  connection_type: string;
  connection_summary: string;
  /** Non-null only for lead GM / staff viewers. */
  internal_notes: string | null;
}

export type StoryLogEntry = StoryLogBeatEntry | StoryLogEpisodeEntry;

export interface StoryLogResponse {
  entries: StoryLogEntry[];
}

// ---------------------------------------------------------------------------
// StoryGMOffer — hand-defined from StoryGMOfferSerializer in serializers.py.
// Not yet reflected in the generated api.d.ts schema because the
// spectacular-generated schema for story-gm-offers was not captured in the
// last schema dump.
// ---------------------------------------------------------------------------

export type StoryGMOfferStatus = 'pending' | 'accepted' | 'declined' | 'withdrawn';

export interface StoryGMOffer {
  id: number;
  story: number;
  offered_to: number;
  offered_by_account: number;
  status: StoryGMOfferStatus;
  message: string;
  response_note: string;
  created_at: string;
  responded_at: string | null;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// GMProfile — hand-defined from GMProfileSerializer in gm/serializers.py.
// The generated type exists in api.d.ts but duplicated here for cleaner
// import paths within the stories module.
// ---------------------------------------------------------------------------

export interface GMProfileData {
  id: number;
  account: number;
  account_username: string;
  level: 'starting' | 'junior' | 'gm' | 'experienced' | 'senior';
  approved_at: string;
}

/** Alias for the full GM profile shape returned by the API. */
export type GMProfile = GMProfileData;

// ---------------------------------------------------------------------------
// OfferStoryToGM request body
// ---------------------------------------------------------------------------

export interface OfferStoryToGMBody {
  gm_profile_id: number;
  message?: string;
}

// ---------------------------------------------------------------------------
// Accept/Decline offer request bodies
// ---------------------------------------------------------------------------

export interface RespondToOfferBody {
  response_note?: string;
}

// ---------------------------------------------------------------------------
// Era — Wave 6 era lifecycle types.
// The generated api.d.ts does not yet include Era (no ViewSet in the
// pre-Wave-6 schema dump). Hand-defined to match EraSerializer in
// world/stories/serializers.py.
// ---------------------------------------------------------------------------

export type EraStatus = 'upcoming' | 'active' | 'concluded';

export interface Era {
  id: number;
  name: string;
  display_name: string;
  season_number: number;
  description: string;
  status: EraStatus;
  activated_at: string | null;
  concluded_at: string | null;
  created_at: string;
  story_count: number;
}

export interface EraCreateBody {
  name: string;
  display_name: string;
  season_number: number;
  description?: string;
  /** Only UPCOMING is allowed on creation. */
  status?: EraStatus;
}
