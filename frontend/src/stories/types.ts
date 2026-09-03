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
/** Routing rule as nested on a Transition (#3563). GM-only on the wire. */
export type TransitionRoutingRule = components['schemas']['TransitionRoutingRule'];

/** Gated fields are optional on the client: the server strips them for viewers without GM text access. */
export type EpisodeList = Omit<components['schemas']['EpisodeList'], 'routing_problems'> & {
  readonly routing_problems?: string[];
};
export type EpisodeDetail = Omit<components['schemas']['EpisodeDetail'], 'routing_problems'> & {
  readonly routing_problems?: string[];
};
export type EpisodeCreate = components['schemas']['EpisodeCreate'];
export type Episode = EpisodeDetail;

// #3425 session prep child rows: one authored opponent line on an ENCOUNTER
// beat, and one authored situation/challenge template on a SITUATION beat
// (exactly one of situation_template/challenge_template is set per row,
// server-enforced XOR). Both are in the generated schema as of #3425.
export type BeatOpponentLine = components['schemas']['BeatOpponentLine'];
export type BeatStagedTemplate = components['schemas']['BeatStagedTemplate'];

// #3569: session prep for an ENCOUNTER beat that is a battle, staged ahead
// of RunBeatAction so the GM can prep the map/roster before running the beat.
export type BeatStagedBattle = components['schemas']['BeatStagedBattle'];
export type BeatStagedBattleUnit = components['schemas']['BeatStagedBattleUnit'];

// #3562: the beat-authoring GM readiness dashboard
// (`GET /api/beats/{id}/readiness/`) and the stakes-contract lock it
// surfaces (`GET /api/stake-activations/?beat=&resolved_at_isnull=true`).
export type BeatReadiness = components['schemas']['BeatReadiness'];
export type StakeContractActivation = components['schemas']['StakeContractActivation'];

// #3562: the beat-authoring consequence pool picker's catalog (list) and
// detail (resolved entries, for the picker's preview) shapes.
export type ConsequencePoolCatalog = components['schemas']['ConsequencePoolCatalog'];
export type ConsequencePoolDetail = components['schemas']['ConsequencePoolDetail'];
export type ConsequencePoolEntry = components['schemas']['ConsequencePoolEntry'];

// #3565: the beat's scenario graph, GM-view only. spectacular cannot
// introspect this SerializerMethodField's shape (it types as a bare
// Record<string, unknown>), so we hand-type it here from the actual
// BeatSerializer.get_scenario() payload.
export interface BeatScenarioSummary {
  template_id: number;
  name: string;
  option_keys: string[];
}

// Beat — single shape with all Phase 2 predicate config fields plus the
// Wave 7 read-context breadcrumb fields (episode_title, chapter_title,
// story_id, story_title), the Wave 12 server-computed can_mark, and the
// #3425 session-prep child row lists. All of these are in the generated
// schema now, so no hand-written extension is needed except `scenario`
// (see BeatScenarioSummary above).
export type Beat = Omit<components['schemas']['Beat'], 'scenario'> & {
  readonly scenario: BeatScenarioSummary | null;
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
export type BeatKind = NonNullable<Beat['kind']>;
export type BeatRisk = NonNullable<Beat['risk']>;
export type StoryScope = NonNullable<Story['scope']>;
export type StoryStatus = NonNullable<Story['status']>;
export type StoryPrivacy = NonNullable<Story['privacy']>;
/** Shared maturity enum (pitch / outline / plot) for Story, Chapter, Episode. */
export type Maturity = NonNullable<components['schemas']['MaturityEnum']>;
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
  /**
   * Authoritative ProgressStatus pointer state:
   * "active" | "waiting_for_gm" | "resting" | "completed".
   * Distinct from `status` (the StoryEpisodeStatus frontier proxy) — lets
   * the banner tell a GM-blocked pause apart from a deliberate rest.
   */
  progress_status: string;
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
  eligible_transitions: Array<{ transition_id: number }>;
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

/** One PENDING canon review in StaffWorkloadView.pending_canon_reviews (#2003/#3304). */
export interface PendingCanonReviewEntry {
  review_id: number;
  story_id: number;
  story_title: string;
  tier: string;
  created_at: string;
  days_aging: number;
}

export interface StaffWorkloadResponse {
  per_gm_queue_depth: PerGMQueueEntry[];
  stale_stories: StaleStoryEntry[];
  stories_at_frontier: FrontierStoryEntry[];
  pending_agm_claims_count: number;
  open_session_requests_count: number;
  /** Map of scope → story count */
  counts_by_scope: Record<string, number>;
  /** Pending canon-impact reviews — the #2003/#3304 review-request queue. */
  pending_canon_reviews: PendingCanonReviewEntry[];
}

// ---------------------------------------------------------------------------
// CanonReviewViewSet (#2003/#3304)
// ---------------------------------------------------------------------------

export type CanonReview = components['schemas']['CanonReview'];

export interface CanonReviewClearBody {
  notes?: string;
}

export interface CanonReviewChangesBody {
  notes: string;
}

// ---------------------------------------------------------------------------
// Action endpoint request shapes (for API functions)
// ---------------------------------------------------------------------------

export interface ResolveEpisodeBody {
  progress_id?: number | null;
  gm_notes?: string;
}

export interface MarkBeatBody {
  outcome: BeatOutcome;
  gm_notes?: string;
  progress_id?: number | null;
}

// Episode maturity promotion (B1). The generated requestBody for
// episodes_promote_create is the full EpisodeDetailRequest because
// spectacular cannot introspect the action's actual body — same known
// pattern as ResolveEpisodeBody. The body is a single MaturityEnum target.
export type EpisodeMaturity = NonNullable<components['schemas']['MaturityEnum']>;

export interface PromoteEpisodeBody {
  target: EpisodeMaturity;
}

// Story scope assignment (B2). assign-to-scope lifts a story out of
// UNASSIGNED. Like promote, the generated requestBody is the full
// StoryDetailRequest; the real action body is the scope + an optional
// owning FK depending on scope.
export type AssignableStoryScope = 'character' | 'group' | 'global';

export interface AssignStoryBody {
  scope: AssignableStoryScope;
  character_sheet?: number;
  gm_table?: number;
}

// StoryNote — OOC authorial memory (append-only). Both shapes are in the
// generated schema; aliased here for cleaner imports within the module.
export type StoryNote = components['schemas']['StoryNote'];
export type StoryNoteRequest = components['schemas']['StoryNoteRequest'];

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
export type Transition = Omit<components['schemas']['Transition'], 'required_outcomes'> & {
  readonly required_outcomes?: TransitionRoutingRule[];
};
export type EpisodeProgressionRequirement = components['schemas']['EpisodeProgressionRequirement'];
export type TransitionRequiredOutcome = components['schemas']['TransitionRequiredOutcome'];

// Enum aliases for Wave 9
export type StoryConnectionType = NonNullable<components['schemas']['ConnectionTypeEnum']>;
export type ReferencedMilestoneType = NonNullable<
  components['schemas']['ReferencedMilestoneTypeEnum']
>;

export interface StoryCreateBody {
  title: string;
  description: string;
  /** Player-facing "The Story So Far" recap (GM-maintained). */
  summary?: string;
  privacy?: StoryPrivacy;
  scope?: StoryScope;
}

export interface ChapterCreateBody {
  story: number;
  title: string;
  description?: string;
  /** Player-facing "The Story So Far" recap (GM-maintained). */
  summary?: string;
  order?: number;
  is_active?: boolean;
}

export interface EpisodeCreateBody {
  chapter: number;
  title: string;
  description?: string;
  /** Player-facing "The Story So Far" recap (GM-maintained). */
  summary?: string;
  /** Player-facing text shown when progress RESTS at this episode. */
  resting_conclusion?: string;
  /** Explicit "this is an ending" marker. */
  is_ending?: boolean;
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

// #3569: write shape for a beat's staged battle (id-less unit_lines create,
// id-carrying unit_lines edit in place - mirrors opponent_lines/staged_templates).
export interface BeatStagedBattleBody {
  id?: number;
  blueprint: number;
  name?: string;
  region?: number | null;
  party_side_role?: 'attacker' | 'defender';
  unit_lines?: Array<{
    id?: number;
    template: number;
    side_role?: 'attacker' | 'defender';
    place_name?: string;
    count?: number;
    order?: number;
  }>;
}

export interface BeatCreateBody {
  episode: number;
  predicate_type?: BeatPredicateType;
  visibility?: BeatVisibility;
  internal_description: string;
  player_hint?: string;
  player_resolution_text?: string;
  order?: number;
  kind?: BeatKind;
  advances?: boolean;
  risk?: BeatRisk;
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
  required_society?: number | null; // FACTION_STANDING_AT_LEAST (society-level)
  required_organization?: number | null; // FACTION_STANDING_AT_LEAST (organization-level)
  required_standing?: number | null; // FACTION_STANDING_AT_LEAST/NPC_REGARD_AT_LEAST minimum raw value
  required_npc_sheet?: number | null; // NPC_REGARD_AT_LEAST

  // #3562 stakes/consequences - the character level this beat's stakes are
  // declared against, the ConsequencePools that fire on each outcome, and
  // an optional MissionTemplate this beat requires (completion engine
  // flips the beat when a launched instance terminates).
  target_level?: number | null;
  success_consequences?: number | null;
  failure_consequences?: number | null;
  expired_consequences?: number | null;
  required_mission?: number | null;

  // #3425 session prep — repeatable child rows. omit to leave untouched on a
  // PATCH; an explicit [] clears every existing row (see BeatSerializer.update()).
  opponent_lines?: BeatOpponentLine[];
  staged_templates?: BeatStagedTemplate[];

  // #3569: session prep for an ENCOUNTER beat that is a battle. omit to
  // leave untouched; null deletes.
  staged_battle?: BeatStagedBattleBody | null;
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

// ---------------------------------------------------------------------------
// Custody protection + clearance (#2001 Task 6/8) — GM-authorable protected
// subjects + the cross-story clearance lifecycle for acting against them.
// ---------------------------------------------------------------------------

/** Shared with world.boundaries's TreasuredSubject — same StakeSubjectKind vocabulary. */
export type SubjectKindEnum = components['schemas']['SubjectKindEnum'];

export type ProtectedSubject = components['schemas']['StoryProtectedSubject'];
export type PaginatedProtectedSubjectList =
  components['schemas']['PaginatedStoryProtectedSubjectList'];

export interface ProtectedSubjectCreateBody {
  story: number;
  subject_kind: SubjectKindEnum;
  subject_sheet?: number | null;
  subject_item?: number | null;
  subject_society?: number | null;
  subject_organization?: number | null;
  subject_label?: string;
  is_active?: boolean;
  notes?: string;
}

export type ProtectedSubjectUpdateBody = Partial<ProtectedSubjectCreateBody>;

/** `Scope77bEnum` in the generated schema — appear/harm/remove custody gates (#2001). */
export type CustodyScope = components['schemas']['Scope77bEnum'];
export type CustodyClearanceStatus = components['schemas']['CustodyClearanceStatusEnum'];
export type CustodyClearance = components['schemas']['CustodyClearance'];
export type PaginatedCustodyClearanceList = components['schemas']['PaginatedCustodyClearanceList'];

export interface RequestClearanceBody {
  protected_subject?: number | null;
  subject_kind?: SubjectKindEnum | null;
  subject_sheet?: number | null;
  subject_item?: number | null;
  subject_society?: number | null;
  subject_organization?: number | null;
  subject_label?: string;
  scope: CustodyScope;
  requesting_story?: number | null;
  requesting_beat?: number | null;
  message?: string;
}

export interface ClearanceDecisionBody {
  response_note?: string;
}

export interface ClearanceResolveBody {
  grant: boolean;
  response_note?: string;
}

// ---------------------------------------------------------------------------
// Stakes (#1770 pillars 1/2/3/5/7/8; ASSET subject + npc_regard_delta +
// transitions_subject_asset widened #3561) - the stakes-contract editor's
// read/write shapes. StakeContractActivation is aliased above (#3562).
// ---------------------------------------------------------------------------

export type Stake = components['schemas']['Stake'];
export type StakeRequestBody = components['schemas']['StakeRequest'];
export type StakeUpdateBody = Partial<StakeRequestBody>;
export type PaginatedStakeList = components['schemas']['PaginatedStakeList'];

export type StakeResolution = components['schemas']['StakeResolution'];
export type StakeResolutionRequestBody = components['schemas']['StakeResolutionRequest'];
export type StakeResolutionUpdateBody = Partial<StakeResolutionRequestBody>;
export type PaginatedStakeResolutionList = components['schemas']['PaginatedStakeResolutionList'];

export type StakeRewardLine = components['schemas']['StakeRewardLine'];
export type StakeRewardLineRequestBody = components['schemas']['StakeRewardLineRequest'];
export type StakeRewardLineUpdateBody = Partial<StakeRewardLineRequestBody>;
export type PaginatedStakeRewardLineList = components['schemas']['PaginatedStakeRewardLineList'];

export type StakeTemplate = components['schemas']['StakeTemplate'];
export type PaginatedStakeTemplateList = components['schemas']['PaginatedStakeTemplateList'];

export type PaginatedStakeContractActivationList =
  components['schemas']['PaginatedStakeContractActivationList'];

/** Per-stake resolution audit row - always MACHINE-resolved since #3561 retired the GM pick. */
export type StakeOutcome = components['schemas']['StakeOutcome'];

/** Player-facing beat-level stakes summary (`GET /api/beats/{id}/stakes-summary/`). */
export type StakesSummary = components['schemas']['StakesSummary'];
export type StakeSummary = components['schemas']['StakeSummary'];

// Enum aliases
export type StakeResolutionColumn = NonNullable<components['schemas']['ColumnEnum']>;
export type StakeRewardSink = NonNullable<components['schemas']['StakeRewardLineSinkEnum']>;
export type StakeSeverity = NonNullable<components['schemas']['SeverityEnum']>;
export type StakeOutcomeMethod = NonNullable<components['schemas']['MethodEnum']>;
export type StakeEscalatesToRisk =
  | components['schemas']['EscalatesToRiskEnum']
  | components['schemas']['BlankEnum'];
export type StakeSetsSubjectLifecycle =
  | components['schemas']['SetsSubjectLifecycleEnum']
  | components['schemas']['BlankEnum'];
export type StakeMachineMatchLifecycleState =
  | components['schemas']['MachineMatchLifecycleStateEnum']
  | components['schemas']['BlankEnum'];

/**
 * `StakeResolution.transitions_subject_asset` (ASSET stakes only). Not a
 * generated enum - the model field is a plain blank-default CharField (no
 * `choices=`), so spectacular types it as a bare `string`; hand-aliased here
 * from `world.assets.constants.AssetStatus`'s recoverable/terminal values
 * (ACTIVE is not a valid transition target, only the three degraded states).
 */
export type AssetTransition = 'compromised' | 'lost' | 'dismissed';
