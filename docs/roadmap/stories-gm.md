# Stories & GM Tables

**Status:** phase-4-complete
**Depends on:** Scenes, Missions, Codex, Relationships, Progression

## Overview
The narrative engine that tracks every character's story arc from CG backstory through every plot beat to retirement or death. GMs manage "tables" of PCs, overseeing their stories and running adventures. GM trust levels determine the scale of impact they can have on the shared world.

## Key Design Points
- **Full arc tracking:** A character's story is traced from CG backstory design through every major plot point. Past entries reference scenes, include player and GM notes, show PC reactions, and track relationship impacts
- **Story beats and steps:** Stories have structured steps summarizing what happened, with links to referenced scenes and mechanical tasks (research needed, enemies to defeat, dungeons to explore, missions to complete)
- **GM Tables:** Virtual tabletop structure. Each GM manages a slice of the world for their assigned PCs. GMs help keep track of PC stories, run adventures, maintain continuity
- **GM progression:** GMs level up through trust ratings, staff promotion, and player feedback. Newbie GMs run low-stakes non-lethal adventures. Higher-tier GMs can run world-changing stories that permanently reshape the setting
- **Task modes:** Story steps can be: missions (solo/async via mission system), research projects (offscreen cron-based rolls), or GM-scheduled sessions
- **Time reconciliation:** Three time modes coexist — canon world time (3:1 game-to-real ratio with character aging), scene time (slow RP pace where 10 minutes IC spans hours of typing), and abstract GM session time (pinned to a specific narrative moment)
- **Coordinated world:** One staffer coordinates all GMs so the game maintains a single connected continuity. Every GM's stories happen in the same world, and actions in one table can affect others
- **Player agency:** Players can reference active stories, see story beats, track what's happening, and have mechanical tasks they can pursue independently between GM sessions

## What Exists

### Pre-Phase-1 Foundation
- **Trust system:** TrustCategory, PlayerTrust, PlayerTrustLevel, StoryTrustRequirement — fully built, orthogonal to the episode engine
- **Feedback models:** StoryFeedback, TrustCategoryFeedbackRating — fully built
- **StoryParticipation** — character involvement tracking, fully built
- **Legacy APIs:** Full viewsets and serializers for the pre-Phase-1 Story/Chapter/Episode shape
- **Tests:** Model tests, view permission tests

### Phase 1 Backend Foundation (complete)

The task-gated episode progression engine is fully implemented in `src/world/stories/`.

- **Era model** — temporal metaplot era tag ("Season N" in player-facing UI); partial unique constraint enforces at most one ACTIVE era at a time; `activated_at`/`concluded_at` timestamps; admin-managed
- **Story extended** — added `scope` (CHARACTER / GROUP / GLOBAL), `character_sheet` FK, `created_in_era` FK
- **Chapter / Episode hierarchy preserved** — `Episode.connection_to_next` and `Episode.connection_summary` removed (semantics moved to Transition)
- **Transition** — first-class directed edge between episodes: `source_episode` FK, `target_episode` nullable FK, `mode` (AUTO / GM_CHOICE), `connection_type` (THEREFORE / BUT), `order` for tie-breaking
- **EpisodeProgressionRequirement** — a beat that must reach `required_outcome` before any outbound transition is eligible (episode-level gate; AND semantics)
- **TransitionRequiredOutcome** — per-transition routing predicate; AND across all rows; OR expressed by multiple transitions
- **Beat** — flat predicate discriminator model with `outcome`, visibility tiers, deadline scaffolding. Phase 1 predicate types: `GM_MARKED`, `CHARACTER_LEVEL_AT_LEAST`
- **BeatCompletion** — append-only audit ledger (beat, character_sheet, outcome, era, gm_notes)
- **EpisodeResolution** — append-only audit ledger (episode, character_sheet, chosen_transition, era, gm_notes)
- **StoryProgress** — per-character pointer into a CHARACTER-scope story's DAG
- **Typed exception hierarchy** — `StoryError` base; concrete: `BeatNotResolvableError`, `NoEligibleTransitionError`, `AmbiguousTransitionError`, `ProgressionRequirementNotMetError`
- **Services:** `evaluate_auto_beats`, `record_gm_marked_outcome`, `get_eligible_transitions`, `resolve_episode`
- **End-to-end integration test** — Crucible "Who Am I?" scenario. 121 stories tests pass; 626 tests across 5-app regression on fresh DB.

### Phase 2 Backend Completion (Waves 1–12 complete)

All Phase 2 model/service/API infrastructure is implemented. 510 stories tests pass on fresh DB.

**Wave 1 — Foundations:**
- New `BeatPredicateType` values: `ACHIEVEMENT_HELD`, `CONDITION_HELD`, `CODEX_ENTRY_UNLOCKED`, `STORY_AT_MILESTONE`, `AGGREGATE_THRESHOLD`
- New `TextChoices`: `StoryMilestoneType` (STORY_RESOLVED / CHAPTER_REACHED / EPISODE_REACHED), `AssistantClaimStatus` (REQUESTED / APPROVED / REJECTED / CANCELLED / COMPLETED), `SessionRequestStatus` (OPEN / SCHEDULED / RESOLVED / CANCELLED)
- `ProgressionRequirementNotMetError` wired into `get_eligible_transitions` (raises instead of returning `[]` when any gate is unmet)
- `StoryProgress` auto-created during CG finalization
- Legacy `Story.is_personal_story` and `Story.personal_story_character` (ObjectDB FK anti-pattern) dropped

**Wave 2 — GROUP + GLOBAL progress models:**
- `GroupStoryProgress(story, gm_table, current_episode)` — one row per GROUP-scope story; unique per (story, gm_table)
- `GlobalStoryProgress(story, current_episode)` — singleton per GLOBAL-scope story; OneToOneField
- Scope-aware helpers: `get_active_progress_for_story`, `advance_progress_to_episode` in `services/progress.py`
- `AnyStoryProgress` type alias widening all services to all three scope progress types

**Wave 3 — New beat predicate types:**
- `ACHIEVEMENT_HELD` — evaluates against `CharacterSheet.cached_achievements_held`; config field: `required_achievement` FK (achievements.Achievement)
- `CONDITION_HELD` — evaluates against active `ConditionInstance` via `CharacterSheet.cached_active_condition_templates`; config: `required_condition_template` FK (conditions.ConditionTemplate)
- `CODEX_ENTRY_UNLOCKED` — evaluates `CharacterCodexKnowledge.status == KNOWN` per RosterEntry; config: `required_codex_entry` FK (codex.CodexEntry)
- `STORY_AT_MILESTONE` — cross-story dependency with `referenced_story`, `referenced_milestone_type` (STORY_RESOLVED / CHAPTER_REACHED / EPISODE_REACHED), `referenced_chapter`, `referenced_episode`; evaluated without a CharacterSheet so usable in GROUP/GLOBAL scope
- Beat config fields are nullable on the model; `clean()` enforces exactly the right fields for each predicate type

**Wave 4 — Aggregate contribution ledger:**
- `AggregateBeatContribution(beat, character_sheet, roster_entry, points, era, source_note)` — per-character contribution ledger
- `AggregateBeatContributionManager.total_for_beat(beat)` — aggregate sum query
- `AGGREGATE_THRESHOLD` predicate: config field `required_points`; evaluates sum via ledger
- `record_aggregate_contribution(*, beat, character_sheet, points, source_note)` — records contribution, re-evaluates beat atomically, creates GROUP-scoped BeatCompletion if threshold crossed (gm_table FK set, character_sheet null)

**Wave 5 — Deadline expiry lifecycle:**
- `Beat.deadline` — DateTimeField (nullable)
- `expire_overdue_beats(now?)` — idempotent bulk sweep; flips UNSATISFIED beats past deadline to EXPIRED
- Lazy invocation in `get_eligible_transitions`: sweeps current episode's overdue beats before evaluating eligibility so routing reflects current deadline state even without a cron

**Wave 6 — Assistant GM claim flow:**
- `AssistantGMClaim(beat, assistant_gm, status, approved_by, rejection_note, framing_note)` model; partial unique constraint prevents duplicate active claims per (beat, assistant_gm)
- `Beat.agm_eligible` BooleanField flag
- Services in `services/assistant_gm.py`: `request_claim`, `approve_claim`, `reject_claim`, `cancel_claim`, `complete_claim`
- `_can_approve` checks Lead GM identity via `story.primary_table.gm_id == approver.pk`; staff override
- Typed exceptions: `BeatNotAGMEligibleError`, `ClaimStateTransitionError`, `ClaimApprovalPermissionError`

**Wave 7 — SessionRequest + Events bridge:**
- `SessionRequest(episode, status, event, open_to_any_gm, assigned_gm, initiated_by_account, notes)` model
- `maybe_create_session_request(progress)` — idempotent; called from write-side services; creates OPEN request when episode has eligible transitions AND GM involvement is required (GM_CHOICE transition OR UNSATISFIED GM_MARKED beat)
- `create_event_from_session_request(*, session_request, name, scheduled_real_time, host_persona, location_id, description, is_public)` — bridges to events system; transitions request to SCHEDULED
- `cancel_session_request(*, session_request)` — OPEN → CANCELLED
- `resolve_session_request(*, session_request)` — SCHEDULED → RESOLVED

**Wave 8 — API ViewSets (base CRUD):**
- `GroupStoryProgressViewSet` — Lead-GM-gated writes; member-filtered queryset
- `GlobalStoryProgressViewSet` — reads for all authenticated; writes staff-only
- `AggregateBeatContributionViewSet` (read-only) — player sees own; story owner sees all; staff sees all
- `AssistantGMClaimViewSet` (read-only) — AGM sees own; story owner sees beat-level; staff sees all
- `SessionRequestViewSet` (read-only) — participant-filtered per scope; staff sees all
- `BeatViewSet` — full CRUD; `BeatSerializer` expanded with all Phase 2 predicate config fields; `validate()` mirrors `Beat.clean()` for 400s on predicate-type invariant violations
- New permission classes and filter classes registered in `urls.py`

**Wave 9 — Story log visibility-filtered serializer:**
- `serialize_story_log(story, requester_role)` — builds ordered log of chapters/episodes/beats with role-gated visibility (SECRET beats hidden for players; HINTED shows `player_hint` only; VISIBLE shows `player_resolution_text` once resolved)
- `/api/stories/{pk}/log/` custom action on StoryViewSet

**Wave 10 — Dashboard endpoints:**
- `/api/stories/my-active/` — player dashboard: all active CHARACTER-scope stories for the requester's character, with status one-liner per story
- `/api/stories/gm-queue/` — Lead GM dashboard: episodes across all tables where progression requirements are met and at least one transition is eligible; ordered by staleness
- `/api/stories/staff-workload/` — staff view: all active stories across all tables with scope and GM attribution
- `compute_story_status_line(progress)` — service function producing human-readable status string for player dashboard

**Wave 11 — Action endpoints:**
- `POST /api/stories/{pk}/resolve-episode/` — fire `resolve_episode` with optional `chosen_transition`
- `POST /api/beats/{pk}/mark/` — `record_gm_marked_outcome` (GM-gated)
- `POST /api/beats/{pk}/contribute/` — `record_aggregate_contribution` (participant-gated)
- `POST /api/assistant-gm-claims/{pk}/approve/` / `reject/` / `complete/` — AGM claim lifecycle transitions
- `POST /api/session-requests/{pk}/create-event/` — bridge to events system
- `POST /api/stories/expire-beats/` — staff-only cron trigger for `expire_overdue_beats`

**Wave 12 — Integration test + docs:**
- `test_integration_phase2.py` — comprehensive GROUP-scope integration test walking all 5 new predicate types, aggregate contributions, deadline expiry, AGM claim flow, and cross-story STORY_AT_MILESTONE reference
- Roadmap, systems index, and MODEL_MAP updated

### Phase 3 Backend Completion (Waves 1–9 complete)

Real-time reactivity: six mutation-time hooks flip beats when gameplay state changes, login catch-up covers offline mutations, and a new general-purpose `world.narrative` app carries IC messages (story updates, atmosphere, visions, happenstance) to characters online and offline.

**Wave 1 — `world.narrative` app foundation:**
- New `world.narrative` app registered under `INSTALLED_APPS`, typed apps list, and `tools/check_type_annotations.py`
- `NarrativeCategory` TextChoices: STORY / ATMOSPHERE / VISIONS / HAPPENSTANCE / SYSTEM
- `NarrativeMessage(body, ooc_note, category, sender_account, related_story, related_beat_completion, related_episode_resolution, sent_at)` — immutable after send
- `NarrativeMessageDelivery(message, recipient_character_sheet, delivered_at, acknowledged_at)` — join table; one message fans out to many recipients; unique per (message, recipient)
- `send_narrative_message(...)` service: atomic create + real-time push to puppeted recipients via `character.msg()` with `|R[NARRATIVE]|n` color tag; offline recipients stay queued
- `deliver_queued_messages(sheet)` — drains queued deliveries at login
- Read API: `GET /api/narrative/my-messages/` (paginated, filterable by category/related_story/acknowledged), `POST /api/narrative/deliveries/{id}/acknowledge/`

**Wave 2 — Stories reactivity service module + story-join snapshot:**
- New `stories.services.reactivity` module exposing five external entry points: `on_character_level_changed` / `on_achievement_earned` / `on_condition_applied` / `on_condition_expired` / `on_codex_entry_unlocked` — each invalidates the relevant cached_property and re-evaluates auto-beats across the character's active stories in all three scopes
- Internal entry point `on_story_advanced(story)` used by Wave 4 cascade
- `create_character_progress` / `create_group_progress` / `create_global_progress` helpers in `services/progress.py` — each creates the progress row and immediately evaluates auto-beats to catch retroactive matches (character already has achievement when story is created)
- `finalize_gm_character` uses `create_character_progress` instead of `StoryProgress.objects.create`

**Wave 3 — External mutation hook wiring:**
- `achievements.services.grant_achievement` fires `on_achievement_earned` for each newly-created CharacterAchievement (idempotent)
- `conditions.services.apply_condition` and `bulk_apply_conditions` fire `on_condition_applied` after ConditionInstance creation
- `conditions.services.remove_condition` fires `on_condition_expired` after instance delete
- `codex.models.CharacterCodexKnowledge.add_progress` fires `on_codex_entry_unlocked` when status transitions from UNCOVERED to KNOWN
- Task 3.1 (progression → stories level-up hook) deferred: no production `CharacterClassLevel` mutation site exists yet; the reactivity entry point is in place for future wiring

**Wave 4 — Internal cascade on `resolve_episode`:**
- `resolve_episode` calls `on_story_advanced(progress.story)` after committing the EpisodeResolution. The hook scans beats with `predicate_type=STORY_AT_MILESTONE` referencing the advanced story and re-evaluates any progress currently on those beats' episodes. Closes the cross-story gate auto-clears design requirement.

**Wave 5 — GROUP/GLOBAL "ANY member" auto-evaluation:**
- `ACHIEVEMENT_HELD`, `CONDITION_HELD`, `CODEX_ENTRY_UNLOCKED`, `CHARACTER_LEVEL_AT_LEAST` now auto-detect for GROUP/GLOBAL scope — the beat flips SUCCESS when any active group member (GROUP) or story participant (GLOBAL) satisfies the predicate. SUCCESS is sticky: a member leaving does not un-flip the beat.
- Reuses the per-sheet predicate helpers so semantics match CHARACTER scope exactly.

**Wave 6 — Stories → narrative integration:**
- New `stories.services.narrative` module composes and fans out `NarrativeMessage` deliveries after BeatCompletion and EpisodeResolution rows are committed
- All three BeatCompletion creation sites (auto-eval, GM-mark, aggregate-threshold crossing) and `resolve_episode` call the notifier
- Beat bodies default to `player_resolution_text`; episode resolution bodies use `transition.connection_summary` with fallback to `episode.summary`
- Recipients resolve per scope: CHARACTER → owning sheet; GROUP → active GMTableMembership personas' sheets; GLOBAL → active StoryParticipation members' sheets

**Wave 7 — Login catch-up:**
- `stories.services.login.catch_up_character_stories(character)` re-evaluates active stories and delivers queued narrative messages
- `Character.at_post_puppet` calls the catch-up service after session puppeting — safety net for any mutation whose real-time hook didn't fire (direct admin action, data import, race condition)

**Wave 8 — Progression-side cache invalidation:**
- No-op for Phase 3: no production service mutates `CharacterClassLevel` yet. The reactivity hook (`on_character_level_changed`) already invalidates the cache defensively, so progression wiring is ready for a future mutation site.

**Wave 9 — End-to-end integration test:**
- `test_integration_phase3.py` — single scenario walking offline mutation → login catch-up → condition apply → resolve_episode cascade → atmosphere message → offline queue → next login delivers. Exercises the complete reactivity + narrative-integration surface.

### Phase 4 Frontend Foundation (complete)

The full React UI for the stories + narrative backend is implemented in
`frontend/src/stories/` and `frontend/src/narrative/`. All 12 waves shipped.

**`frontend/src/narrative/` — IC message delivery UI:**
- API client and React Query hooks for `/api/narrative/my-messages/` and
  `/api/narrative/deliveries/{id}/acknowledge/`
- Inline narrative message rendering in the main game text feed — light red
  visual treatment for `|R[NARRATIVE]|n` tagged messages
- Messages section embedded in the character-sheet page — browseable history
  with category filter and unread-first ordering; acknowledge button per message
- Unread counter badge in the top-level navigation, decrements on acknowledge
- 15 Vitest unit tests covering components and queries

**`frontend/src/stories/` — full player, GM, and staff UI:**
- Player active-stories list (`MyActiveStoriesPage`) — scope group sections
  (Personal / Group / Global) with filter chips
- Story detail page (`StoryDetailPage`) — current episode panel, beat list
  with aggregate progress bar for `AGGREGATE_THRESHOLD` beats, story log
  timeline (visibility-filtered per player/GM role), session-request status
- Aggregate-contribute action dialog (`ContributeBeatDialog`)
- Session-request flow UI: open-to-any-GM and schedule-with-my-GM; status
  card showing request state + scheduled event date
- Lead GM queue dashboard (`GMQueuePage`) — episodes ready to run with scope
  filter, pending AGM claims, assigned session requests
- Mark-beat dialog (`MarkBeatDialog`) for `GM_MARKED` beats
- Resolve-episode dialog (`ResolveEpisodeDialog`) — transition selection for
  `GM_CHOICE` episodes
- Approve/reject AGM claim dialogs (`ApproveClaimDialog`, `RejectClaimDialog`)
- Schedule-session dialog (`ScheduleEventDialog`) bridging session requests to
  the events system
- AGM opportunities page (`AGMOpportunitiesPage`) — browse + request-claim flow
- My AGM claims page (`MyAGMClaimsPage`) — status tabs, cancel/complete actions
- Staff workload dashboard (`StaffWorkloadPage`) — top-line stat cards, per-GM
  queue depth table, stale stories table, frontier stories table, manual
  expire-overdue-beats action
- Story author editor (`StoryAuthorPage`) — full CRUD for Story / Chapter /
  Episode / Beat / Transition; predicate-type-driven beat config form;
  progression requirements editor; episode DAG visualization (React Flow,
  read-only with frontier highlighting)
- Role-gated navigation: player / GM / staff / author sections visible to the
  right audience; unread-narrative badge wires into the nav
- Lazy routing: all page-level imports use `React.lazy()` for route-level code
  splitting
- Error boundaries at the page level for graceful fallbacks
- 173 Vitest unit tests across stories components and queries
- Playwright e2e smoke tests: `e2e/stories-player.spec.ts` (12 tests) and
  `e2e/stories-gm.spec.ts` (20 tests) — verify all routes render without JS
  crash, asset integrity, and no uncaught exceptions

**Known Phase 4 gotchas (for future contributors):**
- `spectacular` cannot introspect `APIView`-based dashboard endpoints (the
  `my-active`, `gm-queue`, `staff-workload` views). Types for these were
  authored manually in `stories/types.ts` rather than generated.
- `GMProfile` is not included in the `/api/user/` account payload; the GM
  navigation section is conditionally shown based on the `gm-queue` endpoint
  returning a non-403 response.
- `StaffRoute` wraps staff-only pages; `ProtectedRoute` wraps player/GM pages.
  Unauthenticated access redirects to `/login` — e2e smoke tests account for
  this by verifying crash-free rendering rather than requiring live auth.

## What's Needed for MVP

### Phase 5: Remaining UI Polish + Missing Lifecycle Tools

- **Covenant leadership model** — required for GROUP-scope stories to have
  meaningful player-driven agency. PC leader / group vote / assigned GM model
  is TBD. Not blocking GROUP-scope backend (GMTable is the current owner),
  but required for full player autonomy.
- **Era lifecycle tooling** — advancing to a new era, handling stories that
  span eras, staff UI for era-advancement flow and Season-N closing ceremonies
- **Dispute / withdrawal state transitions** — personal-story GM change, story
  transfer, player withdrawal from GROUP stories
- **GM ad-hoc narrative message composer** — backend sender endpoint not yet
  built; defer until that endpoint lands alongside the composer UI
- **Mobile-responsive layout polish** — Phase 4 is desktop-first; mobile
  tweaks deferred

### Phase 6+ (blocked on other systems)

- **MISSION_COMPLETE predicate UI** — blocked by the Missions system; the
  `Beat.required_mission` FK scaffold exists in backend, but the Missions
  system itself does not yet exist. Will land alongside missions.
- **Authoring UX richer features** — drag-to-add-transitions in the episode
  DAG, beat-template library, multi-story arc visualizer. Phase 4 delivered
  read-only DAG with frontier highlighting; edit-mode transitions are deferred.

### Pending Wiring (backend)

**`on_character_level_changed` is implemented but unwired in production.**

`stories.services.reactivity.on_character_level_changed(sheet)` exists and correctly
invalidates `sheet.cached_current_level` before re-evaluating `CHARACTER_LEVEL_AT_LEAST`
beats across all active stories. However, no production service currently mutates
`CharacterClassLevel`, so the hook is never called outside tests.

When the progression-services pass creates a `CharacterClassLevel` mutation site, it **must**:
1. Call `sheet.invalidate_class_level_cache()` after the level mutation.
2. Call `stories.services.reactivity.on_character_level_changed(sheet)` to re-evaluate beats.

Until that wiring exists, `CHARACTER_LEVEL_AT_LEAST` predicates only evaluate at login
catch-up (via `catch_up_character_stories`) and when new story progress is created
(retroactive match). Real-time level-up beat flips require the production hook to be wired.
