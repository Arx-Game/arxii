# Stories & GM Tables

**Status:** phase-2-wave-8-complete
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
- **Story extended** — added `scope` (CHARACTER / GROUP / GLOBAL; Phase 1 implements CHARACTER only), `character_sheet` FK (to character_sheets.CharacterSheet), `created_in_era` FK (to stories.Era)
- **Chapter / Episode hierarchy preserved** — `Chapter` and `Episode` keep their existing fields; `Episode.connection_to_next` and `Episode.connection_summary` removed (those semantics moved to Transition)
- **Transition** — first-class directed edge between episodes: `source_episode` FK, `target_episode` nullable FK (null = authoring frontier), `mode` (AUTO fires automatically; GM_CHOICE requires a Lead GM to select), `connection_type` (THEREFORE / BUT narrative flavor), `connection_summary`, `order` for tie-breaking
- **EpisodeProgressionRequirement** — a beat that must reach `required_outcome` before any outbound transition from that episode is eligible (episode-level gate; AND semantics)
- **TransitionRequiredOutcome** — per-transition routing predicate; a beat-outcome pair that must be satisfied for this specific transition to be eligible (AND over all rows on a single transition; OR expressed by creating multiple transitions)
- **Beat** — flat predicate discriminator model on an episode: `predicate_type` selects the concrete type; `outcome` tracks current state; full text layers (`internal_description`, `player_hint`, `player_resolution_text`); `visibility` (HINTED default, SECRET, VISIBLE); `deadline` scaffolded (expiry handling deferred to Phase 3+). Two concrete predicate types in Phase 1:
  - `GM_MARKED` — manually resolved by a Lead GM via `record_gm_marked_outcome`
  - `CHARACTER_LEVEL_AT_LEAST` — auto-evaluated against `CharacterClassLevel`; fires when `character_level >= required_level`
- **BeatCompletion** — append-only audit ledger: one row per (beat, character_sheet) outcome event, capturing `roster_entry` tenure (who was playing), `outcome`, `era`, `gm_notes`, `recorded_at`
- **EpisodeResolution** — append-only audit ledger: one row per episode resolved for a character, capturing `chosen_transition`, `resolved_by` (GMProfile), `era`, `gm_notes`, `resolved_at`
- **StoryProgress** — per-character pointer into a CHARACTER-scope story's DAG: unique per (story, character_sheet); `current_episode` nullable FK (null = frontier or not started); `is_active` flag; `last_advanced_at` auto-updated on each advance
- **Typed exception hierarchy** — `StoryError` base with `user_message` property; concrete subtypes: `BeatNotResolvableError`, `NoEligibleTransitionError`, `AmbiguousTransitionError`, `ProgressionRequirementNotMetError`
- **Services:** `evaluate_auto_beats`, `record_gm_marked_outcome`, `get_eligible_transitions`, `resolve_episode`
- **End-to-end integration test** — Crucible "Who Am I?" scenario: author builds a two-episode story with a level-gate beat and a GM-marked beat → character's progression is initialized → `evaluate_auto_beats` fires the level check → `record_gm_marked_outcome` marks the GM beat → `get_eligible_transitions` confirms both requirements met → `resolve_episode` advances progress and writes full audit trail (BeatCompletion + EpisodeResolution rows). All 121 stories tests pass; 626 tests pass across the 5-app regression suite on a fresh DB.

### Phase 2 Backend Extensions (Waves 1–8 complete)

All model/service infrastructure for Phase 2 is implemented in `src/world/stories/`. 392 stories tests pass on fresh DB.

**Wave 1 — Foundations:**
- New `BeatPredicateType` values: `ACHIEVEMENT_HELD`, `CONDITION_HELD`, `CODEX_ENTRY_UNLOCKED`, `STORY_AT_MILESTONE`, `AGGREGATE_THRESHOLD`
- New `TextChoices`: `StoryMilestoneType`, `AssistantClaimStatus`, `SessionRequestStatus`
- `ProgressionRequirementNotMetError` wired into `get_eligible_transitions` (previously returned `[]`, now raises typed exception)
- `StoryProgress` auto-created during CG finalization
- Legacy `Story.is_personal_story` and `Story.personal_story_character` (ObjectDB FK anti-pattern) dropped

**Wave 2 — GROUP + GLOBAL progress models:**
- `GroupStoryProgress(story, gm_table, current_episode)` — one row per GROUP-scope story; whole GMTable shares the trail; enforced by unique constraint
- `GlobalStoryProgress(story, current_episode)` — singleton per GLOBAL-scope story; enforced by OneToOneField
- Scope-aware helpers: `get_active_progress_for_story`, `advance_progress_to_episode` in `services/progress.py`
- `AnyStoryProgress` type alias widening `resolve_episode` to all three scope progress types

**Wave 3 — New beat predicate types:**
- `ACHIEVEMENT_HELD` — evaluates against `CharacterSheet.cached_achievements_held`
- `CONDITION_HELD` — evaluates against active `ConditionInstance` via `CharacterSheet.cached_active_conditions`
- `CODEX_ENTRY_UNLOCKED` — evaluates against `CodexEntry` per-character discovery
- `STORY_AT_MILESTONE` — cross-story reference with `referenced_story`, `referenced_milestone_type` (STORY_RESOLVED / CHAPTER_REACHED / EPISODE_REACHED), `referenced_chapter`, `referenced_episode`
- All types follow the flat-Beat discriminator pattern: nullable config FKs, `_REQUIRED_CONFIG` dict, `clean()` invariant enforcement

**Wave 4 — Aggregate contribution ledger:**
- `AggregateBeatContribution(beat, character_sheet, roster_entry, points, era, source_note)` — per-character ledger
- `AggregateBeatContributionManager.total_for_beat()` convenience method
- `AGGREGATE_THRESHOLD` predicate type evaluating sum via ledger
- `record_aggregate_contribution` service auto-flips beat outcome when threshold crossed

**Wave 5 — Deadline expiry lifecycle:**
- `expire_overdue_beats(now?)` — idempotent bulk sweep service; flips UNSATISFIED beats past deadline to EXPIRED
- Lazy invocation in `get_eligible_transitions` sweeps current episode's overdue beats before evaluating eligibility

**Wave 6 — Assistant GM claim flow:**
- `AssistantGMClaim(beat, assistant_gm, status, approved_by, framing_note)` model with partial unique constraint (no duplicate active claims per beat-AGM pair)
- `Beat.agm_eligible` flag added
- Services: `request_claim`, `approve_claim`, `reject_claim`, `cancel_claim`, `complete_claim`
- Typed exceptions: `AssistantClaimError`, `AssistantClaimNotApprovableError`, `BeatNotAGMEligibleError`

**Wave 7 — SessionRequest + Events integration:**
- `SessionRequest(episode, story, status, event, open_to_any_gm, assigned_gm, initiated_by_account)` model
- Auto-created via `_maybe_create_session_request(progress)` called from write-side services (mark outcome, record contribution, evaluate auto beats) — no expensive read-path checks
- `create_event_from_session_request` service bridges to the Events system

**Wave 8 — API ViewSets (base CRUD):**
- `GroupStoryProgressViewSet` — CRUD; Lead-GM-gated writes; member-filtered queryset
- `GlobalStoryProgressViewSet` — reads for all authenticated; writes staff-only
- `AggregateBeatContributionViewSet` (read-only) — player sees their own; story owner sees all; staff sees all
- `AssistantGMClaimViewSet` (read-only) — AGM sees their own claims; story owner sees beat-level claims; staff sees all
- `SessionRequestViewSet` (read-only) — participant-filtered per scope; staff sees all
- `BeatViewSet` — full CRUD; `BeatSerializer` expanded with all Phase 2 predicate config fields; `validate()` mirrors `Beat.clean()` surfacing 400s for predicate-type invariant violations
- New permission classes: `IsGroupProgressMemberOrStaff`, `IsGlobalProgressReadableOrStaff`, `IsAggregateBeatContributionReadableOrStaff`, `IsAssistantGMClaimReadableOrStaff`, `IsSessionRequestReadableOrStaff`, `IsBeatStoryOwnerOrStaff`
- New filter classes: `GroupStoryProgressFilter`, `GlobalStoryProgressFilter`, `AggregateBeatContributionFilter`, `AssistantGMClaimFilter`, `SessionRequestFilter`
- All new ViewSets registered in `urls.py`

## What's Needed for MVP

### Phase 2 Remaining: API Surface + Dashboards + Actions (Waves 9–12)

- **Wave 9:** Story log visibility-filtered serializer (HINTED/SECRET/VISIBLE rules per requester role)
- **Wave 10:** Dashboard endpoints — player active-stories (`/api/stories/my-active/`), Lead GM queue (`/api/stories/gm-queue/`), staff workload (`/api/stories/staff-workload/`)
- **Wave 11:** Action endpoints — episode resolve, beat mark, beat contribute, AGM claim lifecycle, session-request event creation, staff expire-overdue-beats trigger
- **Wave 12:** Phase 2 end-to-end integration test + docs update + MODEL_MAP regen

- (Previously listed) ViewSets for Story, Chapter, Episode, Transition, Beat, StoryProgress
  - Read-only for players (their own stories and beats)
  - CRUD for Lead GMs on their assigned stories
  - Full CRUD for staff
- Story log query with visibility filtering — HINTED / SECRET / VISIBLE rules applied at serializer time (SECRET beats omitted for players; HINTED shows player_hint only; VISIBLE shows player_resolution_text once resolved)
- Player "active stories" list with status one-liners ("Ch1 Ep2 — waiting on you", "Ch1 Ep3 — ready to schedule", "Ch1 Ep4 — on hold", etc.)
- Lead GM "episodes ready to run" dashboard — episodes where all progression requirements are met and at least one transition is eligible
- Per-story view for players: story log, active episode panel (hinted beats with progress bar), what's-next call-to-action

### Phase 3+: Advanced Features

- **GROUP scope** — GMTable/covenant-owned progress; shared beat evaluation across group members; covenant leadership model (PC leader / group vote / assigned GM — TBD)
- **GLOBAL scope** — metaplot + aggregate contribution ledger; cross-character threshold beats
- **Additional beat predicate types:** `MISSION_COMPLETE`, `ACHIEVEMENT_HELD`, `AGGREGATE_THRESHOLD`, `STORY_AT_MILESTONE` (cross-story dependency), `CODEX_ENTRY_UNLOCKED`, `CONDITION_HELD`
- **Deadlines** — expiry handling flow; EXPIRED outcome wired to deadline field already scaffolded; story author tooling for deadline management
- **Assistant GM pool** — beat flag marking a beat as AGM-eligible; AGM claim + Lead GM approval; scoped beat access; post-session review workflow
- **Events system integration** — SessionRequest creation triggered when an episode enters "ready to run" state
- **Staff cross-story workload dashboard** — all active stories across all GM tables with world-impact tagging
- **Era-stamping on all remaining time-relevant events** — Era lifecycle management (advance Era, handle overlap with pending episodes)
- **Beat authoring UX beyond Django admin** — in-app flow for GMs to author beats and wire transitions
- **Dispute / withdrawal state transitions** — personal-story GM change, story transfer, player withdrawal
- **Covenant leadership model** — required before GROUP scope lands (PC leader / group vote / assigned GM — TBD)

### Architecture Decisions (recorded for Phase 3+)

These were agreed during the Phase 1 post-merge review but are not yet implemented:

- **Scope progress models are separate per scope.** Phase 1 has
  `StoryProgress(story, character_sheet, current_episode)` for CHARACTER scope.
  Phase 3+ introduces:
  - `GroupStoryProgress(story, group, current_episode)` — one row per story,
    the whole group shares the pointer
  - `GlobalStoryProgress(story, current_episode)` — singleton per story
  Each progress model has exactly one row per story in its scope. Members of
  a group are never split onto different branches; the whole group shares one
  progression trail.

- **`Beat.outcome` is the story's single shared state on the beat.** Not
  per-character. A story has one progression trail; all participants within
  the story's scope see the same outcomes and transitions. `BeatCompletion`
  is the per-character audit ledger recording who contributed what.

- **CHARACTER-scope invariant (now enforced).**
  `StoryProgress.character_sheet` must equal `Story.character_sheet`.
  Validated via `StoryProgress.clean()`.

- **Phase 2 hooks (not yet wired):**
  - `ProgressionRequirementNotMetError` is defined but not raised; Phase 2
    view layer will need to distinguish "no eligible transition because
    progression unmet" from "frontier pause (no transitions authored)".
  - `StoryProgress` records are not auto-created during CG finalization;
    Phase 2 needs a "create on first access" or "create during CG" path.
  - Legacy `Story.is_personal_story` / `Story.personal_story_character` (the
    latter is an ObjectDB FK — an anti-pattern per CLAUDE.md) overlap with
    the new `scope`/`character_sheet` fields. Migrate both away during
    Phase 2 serializer work.

## Notes
