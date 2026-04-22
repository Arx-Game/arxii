# Stories System Design

**Date:** 2026-04-20
**Status:** Design approved, ready for implementation planning
**Supersedes:** The first-pass models under `src/world/stories/` (exploratory — not bound by)

## 1. Purpose & Core Problem

Stories are the single most important engagement system in Arx. Players invest in
their character arcs, their covenant's campaigns, and the metaplot more than any
other content. The game lives or dies on how well this system works.

Arx I's story system died from GM burnout. Players had no gating between GM
sessions, so they waited for GMs to push things forward, felt frustrated, and
lost momentum. GMs felt perpetually behind, got overwhelmed, and burnt out.
Arx II's story system is designed to break that loop.

### Anti-burnout design principles

These are the hard requirements driving every structural choice in this document:

- **Task-gating between GM sessions.** Players always have mechanical work they
  can pursue solo/async between GM-run beats. The GM is never a constant
  bottleneck; they are a climax-delivery mechanism.
- **Frontier-of-authoring as a legitimate pause.** Authors don't finish a story
  upfront. A story that hits an unauthored episode simply parks there until
  content exists. This is a *feature*, not a failure state.
- **Player-side scheduling levers.** Personal-story players can route sessions
  to their assigned GM or open them to "first-available." If their GM is slow,
  they can keep moving.
- **Assistant GM release valve.** Lead GMs can flag specific beats as AGM-OK
  and release them into a queue for other GMs to pick up, distributing
  workload without dividing story authority.
- **Staff cross-story workload visibility.** The staffer coordinating all GMs
  sees every table's queue, spots overload early, and rebalances before
  anyone burns out.

## 2. Terminology

> **Naming note:** In player-facing UI, the metaplot era is called "Season"
> (e.g., "Season 1: Shadows and Light"). Internally — in code, DB, docs — we
> call this `Era` to avoid collision with calendar seasons (spring/summer/fall/winter)
> used by the world clock system. Agents and devs: the model is `Era`.

| Term | Meaning |
|------|---------|
| **Era** | A staff-activated metaplot period. Temporal tag, not a hierarchy parent. Events stamp `created_in_era`, `completed_in_era`, etc. |
| **Story** | A top-level narrative unit with a single progress trail. Has a scope (CHARACTER / GROUP / GLOBAL) that determines who owns the progress. |
| **Chapter** | A major narrative arc within a story. Ordered sequence. |
| **Episode** | The atomic narrative unit. One Episode ≈ one GM session OR one auto-advancing step. Episode-level branching only (no DAG within an episode). |
| **Beat** | A boolean predicate attached to an episode, with a rich outcome state. The gating unit. |
| **Transition** | A first-class guarded edge from one episode to another. Has a routing predicate over beat outcomes and a routing mode (AUTO or GM_CHOICE). |

## 3. Hierarchy & Scope

### Structural shape

```
Era (temporal tag — not a parent)
                ↓ (stamped on Story.created_in_era)
Story (scope: CHARACTER / GROUP / GLOBAL)
  └── Chapter (ordered)
      └── Episode (graph — episodes connect via Transitions)
          ├── Beat(s) — progression requirements AND/OR routing signals
          └── outbound Transition(s) → other Episodes
```

### Scope determines progress ownership

A Story has exactly one progress trail. Scope decides who owns that trail:

- **CHARACTER** — Progress owned by `CharacterSheet`. Continuous across roster
  tenures. Comic-book continuity — no resets on re-roster. `RosterEntry` is
  logged per action (audit trail: "who was playing Crucible when beat X
  completed"), but progress itself is tied to the character identity.
- **GROUP** — Progress owned by a group container (typically `GMTable`, possibly
  a distinct covenant model — TBD). Shared by the group members. Beat
  "kill the warlord" is satisfied once, for the whole group.
- **GLOBAL** — Singleton progress for the game's metaplot. PCs opt-in/opt-out.
  Aggregate beats track per-character contribution. One "Shadows and Light"
  progress record per Era (or one that spans Eras, depending on story).

### Nesting via cross-story reference beats

Stories are not structurally nested. Cross-story dependencies are expressed as
beats whose predicate references another story's state ("Story X has reached
Chapter 3"). Because all beats are boolean predicates, this falls out naturally
— see §5.

### Stories span Eras

A story's `created_in_era` is set once. Chapters, Episodes, and Beats do *not*
have an era parent — they simply stamp the active Era on events (beat
completion, first episode access, episode resolution). A character's personal
story can cross multiple Eras.

## 4. Roles & Visibility

### Role tiers

| Role | Access |
|------|--------|
| **Staff** | Everything across all stories. |
| **Story Owner** (personal-story scope only) | The player. Picks their GM, can withdraw from a GM's table (story follows them), sees their own story dashboard (with hinted/secret rules applied). |
| **Lead GM** | Assigned to a story. Full access: authors new chapters/episodes/beats/transitions, scheduling defaults to them, approves AGM claims on their stories. |
| **Assistant GM** | Claimed a single beat session. Sees *only* that beat's internal description + any notes the Lead GM flagged as relevant + a Lead-GM-written one-paragraph framing. Cannot see the rest of the story. |
| **Player (participant, not owner)** | Sees the Player UX (§7), filtered by visibility rules on beats. |

### Visibility summary

- Authors plan whole chapters invisible to players and to GMs who aren't
  assigned to the story.
- Within a story, the Lead GM and Staff see the full plan graph. AGMs see one
  beat only.
- Players see only the content surfaced by beat visibility rules (§5) plus
  accumulated story-log entries.

## 5. Beat Model

Beats are the atomic gating unit. All beat "kinds" unify as boolean predicates
with rich outcome state.

### Predicate

A beat's predicate is evaluated by the system (auto) or by a GM (GM-marked).
Every conceptual "beat kind" from earlier iterations collapses to a boolean
predicate:

| Conceptual kind | Predicate shape |
|-----------------|-----------------|
| "Complete mission X" | `mission_complete(mission_id)` — auto |
| "Reach level 5" | `character_level_at_least(5)` — auto |
| "Gain the Audere Majora threshold achievement" | `achievement_held(achievement_id)` — auto |
| "Aggregate: 10,000 victory points reached" | `aggregate_threshold(beat_id, 10000)` — auto |
| "Season 3 is active" (cross-story) | `story_at_milestone(other_story_id, milestone)` — auto |
| "Meeting with the Herald" | GM-marked (GM evaluates at session end) |

Implementation detail (for the writing-plans phase): the predicate representation
should be a discriminator mixin per predicate type, not a JSON field. Cross-story
reference beats re-evaluate when the referenced story advances.

### Outcome state

Beats are not just done/not-done. Outcome is one of:

- `unsatisfied` — predicate has never evaluated true
- `success` — predicate evaluated true with a success result
- `failure` — predicate evaluated true with a failure result (mission failed,
  GM judged the scene didn't go the player's way, etc.)
- `expired` — beat had a deadline that passed without success
- `pending_gm_review` — GM-marked beat awaiting GM resolution

Transitions route on these outcomes — success, failure, and expired are all
legitimate routing signals (a failed mission might route to the "bad ending"
branch, an expired deadline might route to an interstitial recovery episode).

### Deadline

Optional per beat. If the deadline passes without success, the beat's outcome
transitions to `expired`. Deadlines use wall-clock time (not IC time) so
players have a real-world sense of urgency.

### Visibility

Per-beat, author-controlled. Three tiers:

| Visibility | While active | On completion |
|------------|--------------|---------------|
| **`hinted`** (default) | Player sees `player_hint` in the active-beats panel | Hint is replaced by `player_resolution_text` in the story log |
| **`secret`** | Does not appear in player UI at all | `player_resolution_text` surfaces in the log — can be authored as vaguely as desired ("Something has awakened in the city's deep places") |
| **`visible`** | `player_hint` is shown as a clear actionable statement | Resolution text surfaces as normal |

Used sparingly, `visible` is mostly for beats around GM scheduling where the
player needs clarity ("Your GM is ready — schedule your session").

### Text layers

Every beat has three text fields:

- `internal_description` — authors / Lead GM / staff view. The real predicate
  and its narrative meaning.
- `player_hint` — what the player sees while the beat is active (if visibility
  allows).
- `player_resolution_text` — what the player sees after the beat completes.
  Becomes part of the story log.

### Aggregate contribution tracking

For aggregate-threshold beats (e.g., "10,000 victory points"), the system tracks
per-character, per-tenure contributions in a ledger. This:

- Powers each character's personal activity view ("You contributed 1,400 points")
- Records which `RosterEntry` made each contribution for audit
- Allows rewards to be distributed proportionally if the story calls for it

## 6. Transitions & Episode Resolution

### Transitions

Transitions are first-class guarded edges between episodes. An Episode has:

- **Progression requirements** — a set of beats that must all be in `success`
  state before *any* outbound transition is eligible. (The "reach level 2 AND
  gain anima ritual AND learn about the academy" pattern.)
- **Outbound transitions** — each with:
  - `target_episode` (may be null if the next episode isn't authored yet —
    natural pause)
  - `routing_predicate` — an expression over beat outcomes (e.g.,
    `mission = success`, `mission = failure AND gm_scene = success`)
  - `mode`: `AUTO` (fires when eligible) or `GM_CHOICE` (Lead GM picks from
    eligible set)

A transition is eligible when:

1. All of the Episode's progression requirements are in `success`, AND
2. Its routing predicate evaluates true against current beat outcomes.

### Episode resolution (pattern G)

When the Lead GM runs an Episode's session:

1. GM marks each GM-marked beat with an outcome (success / failure / partial
   interpreted as success or failure per transition rules) and free-text notes.
2. The system evaluates all transition predicates against current beat
   outcomes.
3. If exactly one AUTO transition is eligible, it fires — Episode advances to
   its target.
4. If multiple transitions are eligible and all are GM_CHOICE (or a mix), the
   GM picks from the eligible set.
5. Both the full set of beat outcomes AND the chosen transition are recorded
   for audit and for the player's story log.

### Episode-level branching only

Beats never chain within an Episode. If a sequence "mission → GM scene → branch"
is needed, the GM scene is its own (possibly tiny) Episode. This keeps:

- Every Episode a uniform unit for the GM dashboard
- Every GM session mapped to exactly one Episode
- The player's timeline readable as a sequence of episodes
- Branching logic concentrated in transitions, not scattered across beats

## 7. Scheduling Flows

### Lead GM queue (default surface, pattern D)

The Lead GM's dashboard shows all episodes across their stories that are
"ready to run" (progression requirements met, at least one transition
eligible, target episode is GM-run). They pick one, schedule via the existing
Events system.

### Scheduling initiation per scope

| Scope | Who initiates | Shape |
|-------|---------------|-------|
| **Personal story** (CHARACTER) | Player. Marks "ready to schedule," chooses to route to their assigned GM OR open to "first-available GM." First-available is a deliberate anti-burnout lever. | Event invites just the player + GM |
| **Group story** (covenant/GMTable) | Lead GM. Coordinates a session with all group members via Events. | Event invites all group members |
| **Global metaplot** (GLOBAL) | Staff. Typical shape: open game-wide event scene, beat predicate references the outcome of that event (e.g., "defeat the siege"). | Event is open to the whole playerbase |

All scheduling flows through the existing Events system (already MVP-complete)
— calendar, invitations, room modifications. The Stories system produces
`SessionRequest` records that the Events system can render as schedulable
events.

### Assistant GM claims

The Lead GM can flag specific beats (typically scene-level ones, not
story-defining ones) as **AGM-OK**. Flagged beats are released into an AGM
queue:

1. An available Assistant GM picks up the beat (across tables — AGM pool is
   game-wide, not per-table).
2. Lead GM or Staff approves the claim.
3. On approval, the AGM gets scoped access: that beat's `internal_description`,
   the Lead-GM-written framing paragraph, and any notes flagged relevant.
4. AGM runs the session, marks outcomes, notes.
5. Lead GM reviews the outcome afterward (can override in exceptional cases).

AGM scope is deliberately narrow. An AGM who runs ten beats across ten
different stories never sees any of those stories' broader plans.

## 8. Player UX

### Active stories list

One-line status per story:

- "Chapter 1, Episode 2 — waiting on you" (beats in progress)
- "Chapter 1, Episode 3 — ready to schedule" (all beats done, scheduling CTA)
- "Chapter 2, Episode 1 — scheduled for [date]" (session booked)
- "Chapter 2, Episode 4 — on hold" (frontier of authoring)

### Per-story view

- **Story log** — real-time event stream of this story's progression. Past
  episodes' summaries, connection summaries (THEREFORE / BUT transitions),
  beat completions (replacing hints with `player_resolution_text`), secret
  beat reveals (vague as author wrote them). Chronological, readable as a
  "comic-book recap." The player can re-read their entire character arc as
  a novel.
- **Active episode panel:**
  - Hinted beats with their hint text
  - Aggregate beats with live progress ("4,300 / 10,000 victory points")
  - Deadline countdowns where applicable
- **What's next CTA:**
  - If ready to schedule: "Schedule with [GM]" or "Open to first-available"
  - If beats pending: implicit "keep playing" (hints guide action for hinted
    beats; secrets give nothing — deliberate)
- **Past episodes** — readable end-to-end.

### Real-time updates

Beat completions surface in the story log the moment they happen — the player
doesn't wait for episode resolution to see progress. Secrets also surface on
completion, with author-controlled vagueness. This creates the "momentum" feel:
you *see* your character's story breathing.

## 9. Author / Lead GM UX

Everything the player sees, PLUS:

- **Full plan graph** — all future episodes, their transitions, beat
  predicates, and internal descriptions, visualized as a graph.
- **Draft episodes** — unpublished content the Lead GM is still writing. Can
  hand off drafts within the story (e.g., player submits their backstory, Lead
  GM drafts their opening chapter).
- **Beat outcome analytics** — across all characters on this story, how often
  does each beat succeed/fail/expire? Identifies beats that are too hard, too
  easy, or dead.
- **Internal descriptions** — the real predicates and meanings, not the
  player-facing hints.
- **Scheduling queue** — ready episodes across all their stories, plus AGM
  queue management (claims pending approval).

## 10. Assistant GM UX

Deliberately narrow:

- The single beat's `internal_description`
- A one-paragraph framing the Lead GM wrote for this session
- Any Lead-GM notes flagged `relevant_to_agm`
- Post-session: a form to mark outcome and leave notes
- Nothing about the story structure, other beats, or past/future episodes

The AGM might run ten beats across ten stories without ever understanding any
single story. That's the design.

## 11. Staff UX

Everything, always, across all stories. Specifically:

- **Cross-story workload dashboard** — every Lead GM's queue, aggregate
  workload per GM, stories without progress in N days, aggregate beat
  contributions, which stories are at their authoring frontier. Designed to
  spot "GM X has 14 pending episodes, redistribute" before burnout hits.
- **Metaplot authoring** — creating Eras, creating GLOBAL-scope stories, open
  game-wide events.
- **Approval authority** for AGM claims (staff can override Lead GM).
- **Retcon controls** — for the rare case where a mistake needs correcting,
  staff can manually adjust progress/outcomes. Audit-logged.

## 12. Integration Points

### Existing systems

- **Events** — actual session scheduling. Stories produce `SessionRequest`
  records; Events renders them as schedulable events with invitations, room
  modifications, calendar integration.
- **GMTable / GMProfile** — Lead GM + their assigned stories. A Story's
  `primary_table` is its home; AGM claims come from a game-wide pool but
  approvals flow through the Lead GM of the home table.
- **CharacterSheet** — source-of-truth anchor for CHARACTER-scope progress.
- **RosterEntry** — per-action audit trail (who was playing the character
  when beat X completed).
- **Missions** — most auto-detected beats reference mission completions.
  Missions produce completion events; beats watch for them. (Missions are
  not-started as of this design.)
- **Scenes** — Episodes can link to recorded scenes (the existing
  `EpisodeScene` bridge). Some beats can reference scene participation
  ("had a scene with NPC X in location Y").
- **Codex** — beats can reference codex entry unlocks.
- **Progression** — beats can reference level thresholds, achievements,
  Audere Majora thresholds.
- **Conditions** — beats can reference condition states where narratively
  relevant.
- **Journals** — players' retellings of completed beats may feed into
  journal entries; TBD whether journals produce beat completion events
  (probably not — avoid load-bearing journal requirements).

### Notification and activity feeds

Beat completions, episode resolutions, scheduling events, and AGM claim
approvals produce activity-feed entries visible to the right audiences (player
for their own progress, Lead GM for their queue, staff for workload).
Notification delivery mechanism is out of scope here — hooks into whatever
notification system exists when this is built.

## 13. Deferred / Open Questions

Flagged for resolution before or during implementation planning:

1. **Covenant leadership model.** Who decides the assigned GM for a covenant's
   stories? PC leader chosen by the covenant / group vote / staff-assigned /
   something else. May vary per covenant.
2. **Beat predicate authoring UX.** How does a non-engineer author write a
   beat predicate? Dropdown of registered predicate types + config form is
   the likely answer, but the authoring surface needs its own design pass.
3. **GM-player dispute / withdrawal flow.** Precise state transitions when a
   player withdraws from a GM's table. Does the story pause while looking
   for a new GM? Is there a staff-mediated fallback? Timeout behavior?
4. **AGM pool precise integration.** Is the AGM queue game-wide (any GM can
   pick up any AGM-flagged beat) or partitioned by GMTable? Claim conflict
   resolution (two AGMs claim simultaneously). AGM reputation/trust gating.
5. **Rewards and payoffs.** XP, legend, reputation, codex entries granted
   from beat completion vs. episode resolution vs. chapter/story completion.
   Ties into progression system work.
6. **Player-driven story authoring.** Can a player write their own story for
   a Lead GM to take on, or is authoring staff/GM-only? If player-authored:
   approval flow for content.
7. **Cross-story reference re-evaluation.** Implementation detail — likely a
   polling-per-session-load plus an event-driven invalidation on referenced
   story advancement. Needs performance design during implementation planning.
8. **Era lifecycle.** Who advances the Era and when? Does advancing Era
   auto-close any open stories, or do they carry forward? (Almost certainly
   carry forward, but needs explicit decision.)
9. **Story termination states.** Cancelled, abandoned, failed — how these
   differ from `completed`. Who can terminate a story and what happens to
   participants.

## 14. Implementation Notes (for the writing-plans phase)

Not binding design decisions, but anticipated shape:

- The existing `src/world/stories/` models are exploratory and will be
  replaced. Keep what works (Story, Chapter, Episode shapes, trust system,
  participation tracking) and replace what doesn't (hierarchy semantics,
  beat model, transition model).
- Use discriminator mixins for predicate types (per CLAUDE.md: prefer
  inheritance over Protocol, no JSON fields for structured data).
- `Era` is a SharedMemoryModel with date range / activation state. Events
  stamp FK to the active era at stamp time.
- `BeatCompletion` is an audit ledger (beat, character_sheet, roster_entry,
  outcome, era, timestamp, gm_notes). Aggregate contributions live here too.
- `EpisodeResolution` is an audit record (episode, beat outcomes snapshot,
  chosen transition, era, timestamp, gm_notes).
- Story log is a chronological read over `BeatCompletion` +
  `EpisodeResolution` filtered by visibility rules, with proper
  `prefetch_related(to_attr=...)` for performance.
- The Events system handles the concrete scheduling — Stories produces
  `SessionRequest` records, Events consumes them.
