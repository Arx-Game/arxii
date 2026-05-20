# Stories System

Structured narrative campaign management: task-gated episode progression, multi-scope (CHARACTER / GROUP / GLOBAL) story arcs, full GM workflow (scheduling, AGM delegation, session requests), and real-time reactivity wired into external systems (achievements, conditions, codex) with login catch-up as a safety net.

**Phase 3 complete.** All backend models, services, reactivity hooks, and API endpoints are implemented. Phase 4 is the React frontend (including the narrative message UI).

**Authoring backbone + authoring API/UI shipped.** The non-linear maturity sketchpad (per-node `maturity`, `StoryScope.UNASSIGNED`, `Episode.resting_conclusion`/`is_ending`, `Beat.kind`/`advances`/`risk`, the WAITING_FOR_GM/RESTING frontier, the per-story `StoryNote` ledger) and the authoring/run-control API + minimal UI are in: `Story.summary` ("The Story So Far"), the GM↔player visibility contract, `POST /api/episodes/{id}/promote/`, `POST /api/stories/{id}/assign-to-scope/`, query-bounded `gm-queue`/`staff-workload`, and the `StoryAuthorPage` run-control surface (promote/assign dialogs, GM Notes panel, inline progress-state banner, nimble +Beat/+Branch). See the Visibility Contract and API sections below.

**Source:** `src/world/stories/`
**API Base:** `/api/stories/`, `/api/chapters/`, `/api/episodes/`, `/api/beats/`, `/api/transitions/`, `/api/story-progress/`, `/api/group-story-progress/`, `/api/global-story-progress/`, `/api/aggregate-beat-contributions/`, `/api/assistant-gm-claims/`, `/api/session-requests/`, `/api/story-notes/`

---

## Enums

```python
# constants.py
from world.stories.constants import (
    EraStatus,              # UPCOMING, ACTIVE, CONCLUDED
    StoryScope,             # UNASSIGNED (new default), CHARACTER, GROUP, GLOBAL
    StoryMaturity,          # PITCH, OUTLINE, PLOT — authoring-completeness of a
                            # Story / Chapter / Episode node; orthogonal to runtime
                            # StoryStatus, per-node, no cross-node ordering constraint
    BeatKind,               # SITUATION, ENCOUNTER, TASK (default), REQUIREMENT —
                            # what a beat *is*; resolution still flows through
                            # predicate_type
    ProgressStatus,         # ACTIVE, WAITING_FOR_GM, RESTING, COMPLETED — finer
                            # pointer state; is_active stays True for ACTIVE /
                            # WAITING_FOR_GM / RESTING; only COMPLETED clears is_active
    BeatPredicateType,      # GM_MARKED, CHARACTER_LEVEL_AT_LEAST, ACHIEVEMENT_HELD,
                            # CONDITION_HELD, CODEX_ENTRY_UNLOCKED, STORY_AT_MILESTONE,
                            # AGGREGATE_THRESHOLD
    StoryMilestoneType,     # STORY_RESOLVED, CHAPTER_REACHED, EPISODE_REACHED
    BeatOutcome,            # UNSATISFIED, SUCCESS, FAILURE, EXPIRED, PENDING_GM_REVIEW
    BeatVisibility,         # HINTED, SECRET, VISIBLE
    TransitionMode,         # AUTO, GM_CHOICE
    AssistantClaimStatus,   # REQUESTED, APPROVED, REJECTED, CANCELLED, COMPLETED
    SessionRequestStatus,   # OPEN, SCHEDULED, RESOLVED, CANCELLED
)

# types.py — pre-Phase-1 (unchanged)
from world.stories.types import (
    StoryStatus,            # ACTIVE, INACTIVE, COMPLETED, CANCELLED
    StoryPrivacy,           # PUBLIC, PRIVATE, INVITE_ONLY
    ParticipationLevel,     # CRITICAL, IMPORTANT, OPTIONAL
    TrustLevel,             # UNTRUSTED (0) .. EXPERT (4)
    ConnectionType,         # THEREFORE, BUT
    AnyStoryProgress,       # StoryProgress | GroupStoryProgress | GlobalStoryProgress
)
```

---

## Hierarchy

```
Era  (temporal tag — not a hierarchy parent)

Story (CHARACTER / GROUP / GLOBAL scope)
  -> Chapter (major arc)
    -> Episode (node in the episode DAG)

Episode <-- Transition --> Episode                 (directed edges; nullable target = authoring frontier)
Episode <-- Beat                                   (predicates attached to an episode)
Episode <-- EpisodeProgressionRequirement          (gates all outbound transitions from this episode)
Transition <-- TransitionRequiredOutcome           (gates this specific transition)
```

---

## Models

### Era

Temporal metaplot tag. One ACTIVE era enforced by partial unique constraint.

| Field | Type | Notes |
|-------|------|-------|
| `name` | SlugField (unique) | |
| `display_name` | CharField | Human-readable |
| `season_number` | PositiveIntegerField | Player-facing "Season N" |
| `description` | TextField | |
| `status` | EraStatus | UPCOMING / ACTIVE / CONCLUDED |
| `activated_at` | DateTimeField (nullable) | |
| `concluded_at` | DateTimeField (nullable) | |

`Era.objects.get_active()` — returns the single ACTIVE era or None.

---

### Story

Top-level campaign container.

| Field | Type | Notes |
|-------|------|-------|
| `title`, `description` | CharField / TextField | `description` = GM-facing pitch/internal authoring text (GM-only — see Visibility Contract) |
| `summary` | TextField (blank) | Player-facing "The Story So Far" — GM-maintained running recap; surfaced to players via the role-gated detail serializers, PITCH-blanked. NOT auto-generated. Added in `0031_story_summary` |
| `status` | StoryStatus | ACTIVE, INACTIVE, COMPLETED, CANCELLED |
| `privacy` | StoryPrivacy | PUBLIC, PRIVATE, INVITE_ONLY |
| `scope` | StoryScope | UNASSIGNED (default) / CHARACTER / GROUP / GLOBAL — `create_*_progress` rejects UNASSIGNED stories |
| `maturity` | StoryMaturity | PITCH (default) / OUTLINE / PLOT — authoring completeness |
| `character_sheet` | FK → character_sheets.CharacterSheet (nullable) | For CHARACTER-scope stories |
| `created_in_era` | FK → stories.Era (nullable) | |
| `covenant` | FK → covenants.Covenant (nullable) | For GROUP-scope stories; informational, not a credit gate |
| `owners` | M2M → accounts.AccountDB | |
| `active_gms` | M2M → gm.GMProfile | |
| `primary_table` | FK → gm.GMTable (nullable) | Lead GM's table; used for AGM claim permission check |
| `required_trust_categories` | M2M through StoryTrustRequirement | |

---

### GM ↔ Player Visibility Contract

Authoring text on Story / Chapter / Episode is split into a **GM-only** lens and
a **player-facing** lens, enforced server-side in two independent places.

**The split:**

| Field | Audience | Notes |
|-------|----------|-------|
| `description` | GM/staff only | The internal authoring "pitch"/intent text. Stripped from the serialized payload for any non-privileged viewer |
| `consequences` (Chapter, Episode) | GM/staff only | Stripped from the serialized payload for any non-privileged viewer (absent on the Story serializer — the pop is a safe no-op there) |
| `summary` | Player-facing | "The Story So Far" running recap. Visible to players, **but blanked to `""` while the node's `maturity == PITCH`** so an unfinished node leaks nothing |

There is **no dedicated `pitch` field** — by design: `description` *is* the GM
pitch, `summary` *is* the player recap. (Resolves design follow-up I-2.)

**Enforcement point 1 — detail serializers.** `StoryDetailSerializer`,
`ChapterDetailSerializer`, and `EpisodeDetailSerializer` each override
`to_representation()` to call the shared `_gm_text_gate(serializer, data, story,
node_maturity)` helper (in `serializers.py`). The helper resolves the viewer's
story-log role via `classify_story_log_viewer_role(user, story)`. If the role is
**not** `VIEWER_ROLE_STAFF` or `VIEWER_ROLE_LEAD_GM` (i.e. player, no_access, or
**no request in context**), it pops `description`/`consequences` and blanks
`summary` when `node_maturity == PITCH`. **Default-deny:** with no request/user
in context the most-restrictive (player) treatment is applied, so GM text never
leaks by default (locked by tests; see `test_views_*` default-deny coverage).
The Chapter gate is keyed on `instance.story`; the Episode gate on
`instance.chapter.story`.

**Enforcement point 2 — `serialize_story_log`.** Independently, the per-beat
story log (`services/story_log.py::serialize_story_log`) gates GM-only beat
internals: `visible_internal_description` (from `beat.internal_description`) and
`visible_gm_notes` / `visible_internal_notes` (from completion/resolution
`gm_notes`) are populated **only** for privileged roles
(`_PRIVILEGED_ROLES = {VIEWER_ROLE_LEAD_GM, VIEWER_ROLE_STAFF}`); players get
`None`. Players also have SECRET-beat `player_hint` suppressed and the log
scoped to their own character's completions/resolutions. `no_access` → empty
list.

The two enforcement points are deliberately separate: serializer
`to_representation` guards node-level authoring prose; `serialize_story_log`
guards per-beat/per-resolution narrative internals.

---

### Chapter

Major arc within a story.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="chapters"` |
| `title`, `description` | CharField / TextField | |
| `order` | PositiveIntegerField | Unique per story |
| `is_active` | BooleanField | |
| `maturity` | StoryMaturity | PITCH (default) / OUTLINE / PLOT — authoring completeness |
| `summary`, `consequences` | TextField | |

---

### Episode

Node in the episode DAG. Transitions are the edges.

| Field | Type | Notes |
|-------|------|-------|
| `chapter` | FK → Chapter | `related_name="episodes"` |
| `title`, `description` | CharField / TextField | |
| `order` | PositiveIntegerField | Unique per chapter |
| `is_active` | BooleanField | |
| `maturity` | StoryMaturity | PITCH (default) / OUTLINE / PLOT — promotion to PLOT gated by `promote_episode_maturity` |
| `resting_conclusion` | TextField | Player-facing text shown when progress RESTS here; required before PLOT promotion |
| `is_ending` | BooleanField | Explicit "this is an ending" marker; satisfies PLOT promotion when there is no outbound transition |
| `summary`, `consequences` | TextField | |

`episode.outbound_transitions` — reverse from Transition.source_episode.
`episode.beats` — reverse from Beat.episode.
`episode.progression_requirements` — reverse from EpisodeProgressionRequirement.episode.

---

### Transition

First-class directed edge in the episode DAG.

| Field | Type | Notes |
|-------|------|-------|
| `source_episode` | FK → Episode | `related_name="outbound_transitions"` |
| `target_episode` | FK → Episode (nullable) | Null = authoring frontier |
| `mode` | TransitionMode | AUTO fires automatically; GM_CHOICE requires explicit pick |
| `connection_type` | ConnectionType | THEREFORE / BUT narrative flavor |
| `connection_summary` | TextField | Short narrative description |
| `order` | PositiveIntegerField | Tie-breaker for eligibility ordering |

`transition.required_outcomes` — reverse from TransitionRequiredOutcome.transition.

---

### EpisodeProgressionRequirement

Beat that must reach `required_outcome` before any outbound transition is eligible (AND across all rows per episode).

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="progression_requirements"` |
| `beat` | FK → Beat | |
| `required_outcome` | BeatOutcome | Default SUCCESS |

---

### TransitionRequiredOutcome

Per-transition routing predicate. All rows on a given transition must be satisfied (AND). OR semantics = multiple transitions.

| Field | Type | Notes |
|-------|------|-------|
| `transition` | FK → Transition | `related_name="required_outcomes"` |
| `beat` | FK → Beat | |
| `required_outcome` | BeatOutcome | |

---

### Beat

Boolean predicate attached to an episode. Flat discriminator model — all config fields are nullable; `clean()` enforces exactly the right fields for each predicate type.

**Core fields:**

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="beats"` |
| `predicate_type` | BeatPredicateType | See below for per-type config fields |
| `outcome` | BeatOutcome | Current state; history in BeatCompletion |
| `visibility` | BeatVisibility | HINTED (default) / SECRET / VISIBLE |
| `internal_description` | TextField | Author/staff view |
| `player_hint` | TextField | Shown while active (HINTED or VISIBLE) |
| `player_resolution_text` | TextField | Shown in story log after completion |
| `deadline` | DateTimeField (nullable) | Expiry triggers EXPIRED outcome via `expire_overdue_beats` |
| `agm_eligible` | BooleanField | True = AGM may claim this beat |
| `order` | PositiveIntegerField | |
| `kind` | BeatKind | SITUATION / ENCOUNTER / TASK (default) / REQUIREMENT — what the beat *is*; resolution still flows through `predicate_type` |
| `advances` | BooleanField | Default True; False = Tangent (recorded for history, never gates a transition) |
| `risk` | PositiveSmallIntegerField | Default 0; plain risk number (meaning assigned later with consequence work). Authoring trust-gated in `BeatSerializer` — only staff may author `risk > 0` |

**Per-predicate config fields (exactly one set should be non-null per predicate type):**

| Predicate type | Required field(s) |
|---------------|------------------|
| `CHARACTER_LEVEL_AT_LEAST` | `required_level` (PositiveIntegerField) |
| `ACHIEVEMENT_HELD` | `required_achievement` FK → achievements.Achievement |
| `CONDITION_HELD` | `required_condition_template` FK → conditions.ConditionTemplate |
| `CODEX_ENTRY_UNLOCKED` | `required_codex_entry` FK → codex.CodexEntry |
| `STORY_AT_MILESTONE` | `referenced_story` FK → Story, `referenced_milestone_type` (StoryMilestoneType), `referenced_chapter` FK → Chapter (nullable), `referenced_episode` FK → Episode (nullable) |
| `AGGREGATE_THRESHOLD` | `required_points` PositiveIntegerField |
| `GM_MARKED` | (no config fields) |

**Scope behaviour for auto-evaluation (`evaluate_auto_beats`):**
- CHARACTER scope: all predicate types evaluated against `progress.character_sheet`.
- GROUP / GLOBAL scope: predicates that require a CharacterSheet (ACHIEVEMENT_HELD, CONDITION_HELD, CODEX_ENTRY_UNLOCKED, CHARACTER_LEVEL_AT_LEAST) are skipped — the GM must mark these manually. STORY_AT_MILESTONE is evaluated without a sheet.
- AGGREGATE_THRESHOLD is write-path triggered (via `record_aggregate_contribution`), not evaluated by `evaluate_auto_beats`.

---

### AggregateBeatContribution

Per-character contribution ledger for AGGREGATE_THRESHOLD beats.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | `related_name="aggregate_contributions"` |
| `character_sheet` | FK → CharacterSheet | Who contributed |
| `roster_entry` | FK → RosterEntry (nullable) | Audit: which tenure was active |
| `points` | PositiveIntegerField | |
| `era` | FK → Era (nullable) | Active era at time of contribution |
| `source_note` | TextField | What produced this contribution |
| `recorded_at` | DateTimeField (auto_now_add) | |

`AggregateBeatContribution.objects.total_for_beat(beat)` → int sum.

---

### AssistantGMClaim

AGM claim lifecycle on an `agm_eligible` beat.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | `related_name="agm_claims"` |
| `assistant_gm` | FK → gm.GMProfile | The claiming AGM |
| `status` | AssistantClaimStatus | REQUESTED → APPROVED/REJECTED/CANCELLED → COMPLETED |
| `approved_by` | FK → gm.GMProfile (nullable) | Lead GM who approved/rejected |
| `rejection_note` | TextField | |
| `framing_note` | TextField | Scene framing authored by Lead GM |
| `created_at` | DateTimeField (auto_now_add) | |
| `updated_at` | DateTimeField (auto_now) | |

Partial unique constraint: no duplicate active claims per (beat, assistant_gm) where status is REQUESTED or APPROVED.

---

### SessionRequest

Scheduling request for an episode that requires GM involvement.

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="session_requests"` |
| `status` | SessionRequestStatus | OPEN → SCHEDULED → RESOLVED (or CANCELLED) |
| `event` | FK → events.Event (nullable) | Set when SCHEDULED |
| `open_to_any_gm` | BooleanField | If True, any GM may claim |
| `assigned_gm` | FK → gm.GMProfile (nullable) | Specifically assigned GM |
| `initiated_by_account` | FK → accounts.AccountDB (nullable) | Who requested the session |
| `notes` | TextField | |
| `created_at` | DateTimeField (auto_now_add) | |
| `updated_at` | DateTimeField (auto_now) | |

---

### BeatCompletion

Append-only audit ledger. One row per beat outcome event. Scope-aware: exactly one of `character_sheet` / `gm_table` / neither is populated.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | `related_name="completions"` |
| `character_sheet` | FK → CharacterSheet (nullable) | CHARACTER scope |
| `gm_table` | FK → gm.GMTable (nullable) | GROUP scope |
| `roster_entry` | FK → roster.RosterEntry (nullable) | Audit: active tenure at time of completion |
| `outcome` | BeatOutcome | |
| `era` | FK → Era (nullable) | Active era at completion |
| `gm_notes` | TextField | |
| `recorded_at` | DateTimeField (auto_now_add) | |

`clean()` enforces scope consistency: CHARACTER → `character_sheet` required; GROUP → `gm_table` required; GLOBAL → both null.

---

### EpisodeResolution

Append-only audit ledger. One row per episode resolved. Scope-aware.

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="resolutions"` |
| `character_sheet` | FK → CharacterSheet (nullable) | CHARACTER scope |
| `gm_table` | FK → gm.GMTable (nullable) | GROUP scope |
| `chosen_transition` | FK → Transition (nullable) | Null = frontier pause |
| `resolved_by` | FK → gm.GMProfile (nullable) | |
| `era` | FK → Era (nullable) | |
| `gm_notes` | TextField | |
| `resolved_at` | DateTimeField (auto_now_add) | |

---

### StoryProgress

Per-character pointer into a CHARACTER-scope story's episode DAG.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="progress_records"` |
| `character_sheet` | FK → CharacterSheet | Must equal `story.character_sheet` (clean() enforced) |
| `current_episode` | FK → Episode (nullable) | Null = not started or frontier |
| `is_active` | BooleanField | Stays True for ACTIVE / WAITING_FOR_GM / RESTING; only COMPLETED clears it |
| `status` | ProgressStatus | ACTIVE (default) / WAITING_FOR_GM / RESTING / COMPLETED — set by `set_progress_status` / `resolve_frontier` |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | Updated on each advance |

Unique per (story, character_sheet).

---

### GroupStoryProgress

Per-GMTable pointer into a GROUP-scope story's episode DAG. The whole table shares one trail.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="group_progress_records"` |
| `gm_table` | FK → gm.GMTable | |
| `current_episode` | FK → Episode (nullable) | |
| `is_active` | BooleanField | Stays True for ACTIVE / WAITING_FOR_GM / RESTING; only COMPLETED clears it |
| `status` | ProgressStatus | ACTIVE (default) / WAITING_FOR_GM / RESTING / COMPLETED |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | |

Unique per (story, gm_table).

---

### GlobalStoryProgress

Singleton pointer per GLOBAL-scope story.

| Field | Type | Notes |
|-------|------|-------|
| `story` | OneToOneField → Story | `related_name="global_progress"` |
| `current_episode` | FK → Episode (nullable) | |
| `is_active` | BooleanField | Stays True for ACTIVE / WAITING_FOR_GM / RESTING; only COMPLETED clears it |
| `status` | ProgressStatus | ACTIVE (default) / WAITING_FOR_GM / RESTING / COMPLETED |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | |

---

### StoryNote

Append-only OOC authorial memory attached to a Story — general story notes and future-idea seeds. Distinct from per-node pitch text. **Never player-visible.** Not promotable; purely informational for the next author. No edit/delete in the API (the ViewSet omits the update/destroy mixins → PATCH/PUT/DELETE return 405).

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="notes"` |
| `author_account` | FK → accounts.AccountDB (nullable, SET_NULL) | Stamped from the requesting account in the serializer; never accepted from client input |
| `body` | TextField | Note content (blank/whitespace-only rejected by serializer) |
| `created_at` | DateTimeField (auto_now_add) | |

No `Meta.ordering` on the model; the ViewSet queryset orders `-created_at`. Access is gated by `CanAccessStoryNotes` (staff, story owner, active GM, or Lead GM of the story's primary table).

---

## Service Functions

All services in `src/world/stories/services/`.

### beats.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `evaluate_auto_beats` | `(progress: AnyStoryProgress) -> None` | Re-evaluates all non-GM_MARKED beats; flips UNSATISFIED beats whose predicate is now met; writes BeatCompletion rows; calls `maybe_create_session_request` on exit |
| `record_gm_marked_outcome` | `(*, progress, beat, outcome, gm_notes="") -> BeatCompletion` | GM manually resolves a GM_MARKED beat; raises `BeatNotResolvableError` if wrong type or invalid outcome |
| `record_aggregate_contribution` | `(*, beat, character_sheet, points, source_note="") -> AggregateBeatContribution` | Records contribution, re-evaluates beat atomically, flips to SUCCESS if threshold crossed |
| `expire_overdue_beats` | `(now=None) -> int` | Idempotent bulk sweep; flips UNSATISFIED past-deadline beats to EXPIRED; returns count |

### transitions.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_eligible_transitions` | `(progress: AnyStoryProgress) -> list[Transition]` | Returns eligible outbound transitions; lazily expires overdue beats; raises `ProgressionRequirementNotMetError` if any gate is unmet |

### episodes.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `resolve_episode` | `(*, progress, chosen_transition=None, gm_notes="", resolved_by=None) -> EpisodeResolution` | Selects/validates transition, creates EpisodeResolution, advances progress; raises `NoEligibleTransitionError` or `AmbiguousTransitionError` on bad state. Now reconciles progress.status after advancing (`_reconcile_status_after_advance`): a non-PLOT target routes through `resolve_frontier` (WAITING_FOR_GM / RESTING), a PLOT target clears a stale frontier status back to ACTIVE, a None target is left untouched. Distinguishes a genuine authoring frontier (current episode has *no* outbound transitions → `resolve_frontier`) from a transient routing block (outbound transitions exist but none routable yet → status stays ACTIVE) before re-raising `NoEligibleTransitionError` |
| `_reconcile_status_after_advance` | `(progress: AnyStoryProgress) -> None` | Internal; called by `resolve_episode` after the atomic advance — see above |

### progress.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_active_progress_for_story` | `(story: Story) -> AnyStoryProgress \| None` | Dispatches on scope: CHARACTER → first active StoryProgress; GROUP → first active GroupStoryProgress; GLOBAL → global_progress OneToOne accessor |
| `advance_progress_to_episode` | `(progress, target_episode) -> None` | Updates `current_episode` and auto-stamps `last_advanced_at` |
| `create_character_progress` | `(*, story, character_sheet, current_episode=None) -> StoryProgress` | Creates progress + immediately `evaluate_auto_beats` to catch retroactive matches (Phase 3). Raises `StoryNotAssignedError` if `story.scope == UNASSIGNED` |
| `create_group_progress` | `(*, story, gm_table, current_episode=None) -> GroupStoryProgress` | GROUP equivalent of `create_character_progress`; same UNASSIGNED guard |
| `create_global_progress` | `(*, story, current_episode=None) -> GlobalStoryProgress` | GLOBAL equivalent; same UNASSIGNED guard |

### frontier.py

When a player cannot advance, decide whether the story is WAITING_FOR_GM (immature content remains — the author intends more) or RESTING (nothing authored remains — deliberately ambiguous, never COMPLETED).

| Function | Signature | Description |
|----------|-----------|-------------|
| `set_progress_status` | `(progress: AnyStoryProgress, status: ProgressStatus) -> None` | Sets `status` on any progress type; COMPLETED also clears `is_active`, every other status keeps `is_active` True. Saves `status`, `is_active`, `last_advanced_at` |
| `resolve_frontier` | `(progress: AnyStoryProgress) -> None` | Sets WAITING_FOR_GM (any Episode in the story still PITCH/OUTLINE) or RESTING (all PLOT). Never sets COMPLETED — only an explicit staff/owner action does that. Caller must only invoke when the player genuinely cannot advance. The immature-content check is a story-wide heuristic ("any Episode below PLOT"); per-DAG-reachability refinement is a documented follow-up |

### maturity.py

Maturity-promotion validation. Forward promotion is gated by minimal per-node content rules; lateral moves and demotion are always allowed (non-linear sketchpad).

| Function | Signature | Description |
|----------|-----------|-------------|
| `promote_episode_maturity` | `(episode: Episode, target: StoryMaturity) -> Episode` | Sets `episode.maturity` to `target`. Promotion *to PLOT* requires a non-empty `resting_conclusion` AND either an outbound transition or `is_ending`; otherwise raises `MaturityPromotionError`. Returns the saved episode. **Exposed via `POST /api/episodes/{id}/promote/`**, whose `PromoteEpisodeInputSerializer.validate()` mirrors this exact PLOT-gate so the violation is a 400 (not a service-raised 500). *Note: the gate predicate is currently duplicated between this service and the serializer — extracting a shared predicate is a recorded follow-up* |

### reactivity.py (Phase 3)

External-facing entry points called by achievements, conditions, codex, and (future) progression services after mutations. Each hook invalidates the relevant `CharacterSheet` cache and re-evaluates auto-beats across the character's active stories across all three scopes (CHARACTER via `StoryProgress`; GROUP via `GMTableMembership.left_at__isnull=True`; GLOBAL via active `StoryParticipation`).

| Function | Signature | Description |
|----------|-----------|-------------|
| `on_character_state_changed` | `(sheet) -> None` | General-purpose re-evaluation entry point; called by the specific hooks below |
| `on_character_level_changed` | `(sheet) -> None` | Called by progression after `CharacterClassLevel` mutation; invalidates class-level cache |
| `on_achievement_earned` | `(sheet, achievement) -> None` | Called by `achievements.services.grant_achievement`; invalidates achievement cache |
| `on_condition_applied` | `(sheet, condition_instance) -> None` | Called by `conditions.services.apply_condition` after instance creation |
| `on_condition_expired` | `(sheet, condition_template) -> None` | Called by `conditions.services.remove_condition` after instance delete |
| `on_codex_entry_unlocked` | `(sheet, codex_entry) -> None` | Called by `CharacterCodexKnowledge.add_progress` when status flips UNCOVERED→KNOWN |
| `on_story_advanced` | `(story) -> None` | Internal cascade called by `resolve_episode`; re-evaluates STORY_AT_MILESTONE beats referencing the advanced story |

### login.py (Phase 3)

Hook called from `Character.at_post_puppet`.

| Function | Signature | Description |
|----------|-----------|-------------|
| `catch_up_character_stories` | `(character) -> None` | Re-evaluates auto-beats across active stories and drains queued `NarrativeMessageDelivery` rows via `narrative.services.deliver_queued_messages`; safety net for mutations whose real-time hook didn't fire while offline |

### narrative.py (Phase 3)

Stories → narrative integration. Composes and fans out `NarrativeMessage` deliveries after BeatCompletion and EpisodeResolution rows are committed.

| Function | Signature | Description |
|----------|-----------|-------------|
| `notify_beat_completion` | `(completion, progress) -> None` | Fans out a NarrativeMessage with `category=STORY`, `related_beat_completion` populated, body defaulting to `beat.player_resolution_text` |
| `notify_episode_resolution` | `(resolution, progress) -> None` | Fans out a NarrativeMessage with `related_episode_resolution` populated, body using `transition.connection_summary` with fallback to `episode.summary` |

Called from all three BeatCompletion creation sites (`_evaluate_and_record_beat`, `record_gm_marked_outcome`, `record_aggregate_contribution`) and `resolve_episode`.

### assistant_gm.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `request_claim` | `(*, beat, assistant_gm, framing_note="") -> AssistantGMClaim` | AGM requests claim; raises `BeatNotAGMEligibleError` if beat not flagged |
| `approve_claim` | `(*, claim, approver, framing_note=None) -> AssistantGMClaim` | Lead GM approves; raises `ClaimStateTransitionError` / `ClaimApprovalPermissionError` |
| `reject_claim` | `(*, claim, approver, note="") -> AssistantGMClaim` | Lead GM rejects |
| `cancel_claim` | `(*, claim) -> AssistantGMClaim` | AGM cancels own claim (REQUESTED only) |
| `complete_claim` | `(*, claim, completer) -> AssistantGMClaim` | Lead GM marks APPROVED claim COMPLETED |

### scheduling.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `maybe_create_session_request` | `(progress: AnyStoryProgress) -> SessionRequest \| None` | Idempotent; creates OPEN SessionRequest when episode has eligible transitions AND GM involvement is needed |
| `create_event_from_session_request` | `(*, session_request, name, scheduled_real_time, host_persona, location_id, description="", is_public=True) -> Event` | Bridges OPEN SessionRequest to Events system; transitions to SCHEDULED |
| `cancel_session_request` | `(*, session_request) -> SessionRequest` | OPEN → CANCELLED |
| `resolve_session_request` | `(*, session_request) -> SessionRequest` | SCHEDULED → RESOLVED |

### story_log.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `serialize_story_log` | `(story, requester_role) -> list[dict]` | Builds ordered chapter/episode/beat log with role-gated visibility |

### dashboards.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `compute_story_status` | `(progress: AnyStoryProgress) -> StoryStatusSummary` | Structured status summary (StoryEpisodeStatus + position + scheduling info); callers render their own labels. The service returns no human-readable strings |
| `compute_story_status_line` | `(progress: AnyStoryProgress) -> str` | **Added in the authoring backbone** (it did not exist before — earlier doc/plan references to it were aspirational). Player-facing one-liner for the dashboard. Branches on `progress.status` FIRST: WAITING_FOR_GM / RESTING / COMPLETED return deliberately-ambiguous copy that never implies finality at a pause/rest and is reassuring at WAITING_FOR_GM; ACTIVE describes the current position from `compute_story_status`. GM/staff dashboards use the structured status + `last_advanced_at`, not this string |

---

## Exceptions

```python
from world.stories.exceptions import (
    StoryError,                         # Base; has user_message property
    BeatNotResolvableError,             # Wrong predicate type or invalid outcome
    NoEligibleTransitionError,          # No eligible transitions; or chosen_transition not valid
    AmbiguousTransitionError,           # Multiple eligible; or GM_CHOICE without explicit pick
    ProgressionRequirementNotMetError,  # Episode-level gate not satisfied
    BeatNotAGMEligibleError,            # beat.agm_eligible is False
    ClaimStateTransitionError,          # Claim not in expected state for transition
    ClaimApprovalPermissionError,       # Approver is not Lead GM or staff
    SessionRequestNotOpenError,         # Session request not in expected state
    StoryNotAssignedError,              # create_*_progress against an UNASSIGNED-scope story
    MaturityPromotionError,             # Episode failed PLOT-promotion validation
)
```

Never pass `str(exc)` to API responses — use `exc.user_message`.

---

## API Endpoints

### Dashboard / Custom Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/api/stories/{pk}/log/` | Participant or staff | Story log with visibility filtering |
| GET | `/api/stories/my-active/` | Authenticated | Player's active CHARACTER-scope stories |
| GET | `/api/stories/gm-queue/` | GMProfile required | Lead GM's episodes-ready-to-run dashboard. Response includes `episodes_ready_to_run`, `pending_agm_claims`, `assigned_session_requests`, and `waiting_for_gm` (active progress rows parked at `ProgressStatus.WAITING_FOR_GM` — no eligible transition yet, a dropped ball — each with `last_advanced_at` + `days_waiting`). **Query-bounded** (follow-up #2/#3 resolved): `_collect_gm_queue` hoists every per-story lookup into a batched pass keyed on candidate episodes via the `GMQueueBuckets` / `_GMQueueInputs` dataclasses, so total query count is a small constant independent of how many stories the GM leads. Locked by `assertNumQueries` in `tests/test_views_gm_queue.py`. Response shape/values/order unchanged from the pre-bounding loop |
| GET | `/api/stories/staff-workload/` | Staff | Cross-story metrics: per-GM queue depth, `stale_stories`, `stories_at_frontier`, and `stories_waiting_for_gm` (WAITING_FOR_GM progress across all three scopes, any age, with `days_waiting`). **Query-bounded** (follow-up #2 resolved): per-GM queue depth assembled from batched inputs via the `_StaffPerGMInputs` dataclass (one query per map, zero per-GM/per-story queries); the stale / waiting / frontier sections are one `.values()` scan per progress model (fixed three queries each), not per-row. Locked by `assertNumQueries` in `tests/test_views_staff_workload.py`. **Per-GM membership is status-agnostic**: the per-GM section iterates the full `GMProfile.objects.filter(tables__primary_stories__isnull=False).distinct()` set (a GM whose only primary story is non-active still appears with `episodes_ready=0` + their status-agnostic `pending_claims`) — preserved/restored after the C2 bounding refactor briefly narrowed it to active-lead-story GMs |
| POST | `/api/stories/{pk}/resolve-episode/` | Story owner or staff | Fire `resolve_episode`; body: `{chosen_transition?}` |
| POST | `/api/stories/expire-beats/` | Staff | Trigger `expire_overdue_beats` |
| POST | `/api/stories/{pk}/assign-to-scope/` | Lead GM of `story.primary_table` or staff (`IsLeadGMOnStoryOrStaff`) | Lift a story out of UNASSIGNED. Body: `{scope, character_sheet?, gm_table?}`. Sets `Story.scope` and creates the scope-appropriate progress record atomically (CHARACTER → also sets `story.character_sheet` + `create_character_progress`; GROUP → `create_group_progress`; GLOBAL → `create_global_progress`). Returns the updated `StoryDetailSerializer`. **400 if the story is not currently UNASSIGNED** (re-assignment is rejected by `AssignStoryInputSerializer.validate()` — would otherwise 500 on a duplicate progress row or silently corrupt scope). **400 on a scope↔target invariant violation** (CHARACTER requires `character_sheet` and forbids `gm_table`; GROUP requires `gm_table` and forbids `character_sheet`; GLOBAL forbids both; UNASSIGNED is not an accepted input scope — excluded from the ChoiceField) |

### Episode Custom Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/episodes/{pk}/promote/` | Lead GM of `story.primary_table` or staff (`IsLeadGMOnStoryOrStaff`) | Set the episode's authoring maturity. Body: `{target}` (a `StoryMaturity` value). Calls `promote_episode_maturity`; returns the updated `EpisodeDetailSerializer`. The **PLOT-gate** is mirrored in `PromoteEpisodeInputSerializer.validate()` so a violation surfaces as a clean **400** (`MaturityPromotionError().user_message`) instead of a service-raised 500. The gate fires **only** on an upward move *to* PLOT (lateral moves and demotions are unvalidated by design — non-linear sketchpad); it requires a non-empty `resting_conclusion` AND (≥ 1 outbound transition OR `is_ending`) |

### Beat Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/beats/{pk}/mark/` | Story owner (GM) | `record_gm_marked_outcome`; body: `{outcome, gm_notes?}` |
| POST | `/api/beats/{pk}/contribute/` | Story participant | `record_aggregate_contribution`; body: `{points, source_note?}` |

### AGM Claim Lifecycle

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/assistant-gm-claims/{pk}/approve/` | Lead GM or staff | `approve_claim` |
| POST | `/api/assistant-gm-claims/{pk}/reject/` | Lead GM or staff | `reject_claim` |
| POST | `/api/assistant-gm-claims/{pk}/complete/` | Lead GM or staff | `complete_claim` |

### Session Request Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/session-requests/{pk}/create-event/` | Story owner | Bridge to events system |

### Standard ViewSet CRUD

All ViewSets support standard REST verbs (GET list/detail, POST create, PATCH/PUT update, DELETE) subject to permission class rules.

| ViewSet | Base URL | Writable by |
|---------|----------|-------------|
| StoryViewSet | `/api/stories/` | Story owners, staff |
| ChapterViewSet | `/api/chapters/` | Story owners, staff |
| EpisodeViewSet | `/api/episodes/` | Story owners, staff |
| BeatViewSet | `/api/beats/` | Story owners, staff |
| TransitionViewSet | `/api/transitions/` | Story owners, staff |
| StoryProgressViewSet | `/api/story-progress/` | Story owners, staff |
| GroupStoryProgressViewSet | `/api/group-story-progress/` | Lead GM of table, staff |
| GlobalStoryProgressViewSet | `/api/global-story-progress/` | Staff only |
| AggregateBeatContributionViewSet | `/api/aggregate-beat-contributions/` | Read-only |
| AssistantGMClaimViewSet | `/api/assistant-gm-claims/` | Read-only (AGM creates via custom action) |
| SessionRequestViewSet | `/api/session-requests/` | Read-only |
| StoryNoteViewSet | `/api/story-notes/` | **Append-only** (list + retrieve + create only; PATCH/PUT/DELETE → 405). Access gated by `CanAccessStoryNotes`: staff, story owner, active GM, or Lead GM of the story's primary table. `?story=<id>` filter (`StoryNoteFilter`). `author_account` stamped server-side. OOC authorial memory — never plain-player-visible |

---

## Cross-App Integration

| System | Integration point |
|--------|------------------|
| **character_sheets** | `StoryProgress.character_sheet`, `BeatCompletion.character_sheet`; `CharacterSheet.cached_achievements_held` and `cached_active_condition_templates` for beat evaluation; `CharacterSheet.current_level` for `CHARACTER_LEVEL_AT_LEAST` |
| **achievements** | `Beat.required_achievement` FK; `CharacterAchievement` queried for `ACHIEVEMENT_HELD` evaluation; `sheet.invalidate_achievement_cache()` must be called after granting achievements |
| **conditions** | `Beat.required_condition_template` FK; `ConditionInstance` queried for `CONDITION_HELD` evaluation; `sheet.invalidate_condition_cache()` must be called after applying conditions |
| **codex** | `Beat.required_codex_entry` FK; `CharacterCodexKnowledge.status == KNOWN` per RosterEntry for `CODEX_ENTRY_UNLOCKED` evaluation |
| **gm** | `GMProfile` for `resolved_by`, `assigned_gm`, AGM claim actors; `GMTable` for GROUP scope progress and primary_table permission check; `GMTableMembership` for queryset filtering |
| **roster** | `RosterEntry` used in `BeatCompletion.roster_entry` and `AggregateBeatContribution.roster_entry` for audit trail |
| **events** | `SessionRequest.event` FK; `create_event_from_session_request` calls `events.services.create_event` |
| **scenes** | `EpisodeScene` links scenes to episodes; `Persona` used as `host_persona` for session event creation |
| **classes** | `CharacterClassLevel` queried for `CHARACTER_LEVEL_AT_LEAST` evaluation |
| **Era** | `BeatCompletion.era`, `EpisodeResolution.era`, `AggregateBeatContribution.era` — stamped with active era at event time; `Story.created_in_era` for grouping |

---

## Pre-Phase-1 Models (unchanged)

### Trust System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TrustCategory` | Dynamic trust categories | `name`, `display_name`, `description`, `is_active` |
| `PlayerTrust` | Aggregate trust profile | `account` (OneToOne AccountDB), `gm_trust_level` |
| `PlayerTrustLevel` | Per-category trust level | `player_trust`, `trust_category`, `trust_level`, feedback counts |
| `StoryTrustRequirement` | Trust gate for story join | `story`, `trust_category`, `minimum_trust_level` |

### Participation & Feedback

| Model | Purpose |
|-------|---------|
| `StoryParticipation` | Character involvement in a story |
| `StoryFeedback` | Post-story trust-building feedback |
| `TrustCategoryFeedbackRating` | Per-category rating within feedback |
| `EpisodeScene` | Links scenes to episodes |
