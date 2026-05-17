# Stories Authoring Framework — Design

**Date:** 2026-05-15
**Status:** Validated design, ready for implementation planning
**Topic:** The shape of stories, how staff/GMs author them, and the runnable backbone
**Relates to:** `docs/roadmap/stories-gm.md`, `docs/systems/stories.md`

---

## 1. Why this exists

Stories has shipped Phases 1–5 (backend engine, reactivity, frontend, GM/staff
workflow). That work laid the *groundwork* — a task-gated episode DAG with
predicate beats — but it is not the system we actually want. This design
reshapes the authoring model around how staff and GMs *think about and grow
narrative*, and defines a backbone that is **runnable end to end on day one**,
with every richer behavior resolvable by a placeholder until its dedicated
engine lands.

**Proof-of-concept success criterion:** staff can author a story and run it
from beginning to end, and a starting GM can do the same.

### Deltas from what is built

| Built today | This design |
|---|---|
| `Beat` is a flat predicate discriminator (a boolean gate) | `Beat` is the **umbrella** for anything that happens in an episode, with a `kind` and an `advances` flag |
| Runtime status only (ACTIVE/INACTIVE/COMPLETED/CANCELLED) | A new orthogonal **maturity ladder** (Pitch → Outline → Plot) per node |
| Scope = CHARACTER / GROUP / GLOBAL | Adds **UNASSIGNED** as the creation default |
| No reward/risk concept | A plain **`risk` integer** per beat + a trust gate at authoring time |
| No authorial memory | A per-story **append-only notes ledger** |
| Reaching unauthored content is undefined | Explicit **WAITING_FOR_GM vs. RESTING** frontier behavior |

---

## 2. Scope of this design

**In scope (the backbone, built now):** the Story/Chapter/Episode/Beat shape;
beat `kind` + `advances`; per-node maturity; the frontier behavior; scope
including UNASSIGNED; the `risk` integer + trust gate; the notes ledger;
the authoring workflow and the three viewing lenses; the seams that let each
follow-up slot in without reshaping.

**Explicitly deferred (own later brainstorms — see §10):** the
Mission/Challenge resolution engine; Situation/Encounter live-session
resolution and Sessions; consequence + reward *computation* (where risk
numbers get names and meaning); GM leveling / the trust→risk earning curve;
the covenant entity.

Every richer beat resolves via a **placeholder GM-mark** until its engine
exists, so the backbone is runnable immediately and each follow-up swaps a
placeholder for a real engine with no schema change.

---

## 3. The shape

Hierarchy is unchanged: **Story → Chapter → Episode**, with Episodes forming a
branching DAG via the existing `Transition` edges. All existing machinery —
`BeatCompletion`, `EpisodeProgressionRequirement`, `TransitionRequiredOutcome`,
reactivity hooks, narrative fan-out — is reused untouched.

### Beat becomes the umbrella, in place

We extend the existing `Beat` model rather than rebuild it. Add:

- **`kind`** ∈ { `SITUATION`, `ENCOUNTER`, `TASK`, `REQUIREMENT` }
  - **Situation** — a challenge inside a GM-run session (escaping a death trap).
  - **Encounter** — a threat inside a GM-run session (a zombie horde).
  - **Task** — an *automated* objective (assassinate the corrupt official),
    resolved by the player picking checks against their capabilities and
    branching to outcomes. Tasks resolved by the future engine = **Missions**.
  - **Requirement** — a gate that must be met before the episode can advance.
- **`advances`** (bool). `advances=False` is a **Tangent**: it is recorded
  against the current episode for history and shown in the player log, but it
  never gates a transition (e.g., an NPC lore conversation).

The existing predicate types (`GM_MARKED`, `ACHIEVEMENT_HELD`,
`CONDITION_HELD`, …) stop being the top-level concept. They become the
*resolution mechanism* beneath `TASK` / `REQUIREMENT` beats — the
predicate-driven beat form becomes a **sub-config of those kinds**, not the
primary axis. `SITUATION` / `ENCOUNTER` beats resolve via placeholder GM-mark
until their engines land.

---

## 4. The maturity ladder

A `maturity` field ∈ { `PITCH`, `OUTLINE`, `PLOT` } on **Story, Chapter, and
Episode independently**.

- **Pitch** — prose intent only. Never player-visible. The least-finished
  state: "here is what I, as the author, am thinking." Can describe the far
  future ("if a PC plays five years and hits level 16…") — a showrunner stub
  left for whoever picks the story up.
- **Outline** — rough episode stubs within a chapter; the DAG starts taking
  shape (episodes + draft transitions) but beats may not exist yet.
- **Plot** — the "hard mechanical drafting" pass: beats fully defined with
  `kind`, `advances`, `risk`, hint/visibility/resolution text; transitions and
  progression requirements wired; the required `resting_conclusion` written.

### Non-linear sketchpad — the core authoring principle

Maturity is per-node and **fully independent**. There is **no** constraint
that:

- a parent be as mature as its children (or vice versa),
- earlier-`order` nodes be more mature than later ones,
- a node be **reachable in the DAG** to exist or be stubbed.

An author can create a Chapter 3 pitch with zero episodes and no transition
leading to it; pitch two episodes of Chapter 1; skip to a Chapter 2 pitch;
then come back and fill in details — in any order. The existing model already
tolerates this (`Transition.target` is nullable; an episode with no inbound
edge is simply unreachable-but-valid).

**The work here is negative:** the editor must add *no* validation that
enforces order, reachability, or a top-down/bottom-up style. The only hard
rule is the minimal per-node runnable check at Plot promotion (§5).
Reachability is purely a *runtime* concern, handled gracefully by §6.
Disconnected nodes render as such in the DAG view (reuse the existing frontier
highlighting), never as errors.

---

## 5. Authoring, concretely

A GM creating a story, start to finish:

1. **Create** — title + scope (defaults **UNASSIGNED**). Born at maturity
   **Pitch**: a title and a "here's what I'm thinking" prose box, never
   player-visible.
2. **Pitch** — write the story-level pitch; optionally add Chapter stubs (each
   born at Pitch — just pitch text). Far-future ideas go here as chapter
   pitches or as notes-ledger entries.
3. **Outline** — promote to Outline; flesh chapters into rough Episode stubs
   and draft the DAG (episodes + THEREFORE/BUT transitions) without beats yet.
   Each episode can carry its own pitch.
4. **Plot** — promote an episode to Plot: add beats (`kind`, `advances`,
   `risk`, existing hint/visibility/resolution text); wire transitions and
   progression requirements; write the required `resting_conclusion`. Beats
   resolve via placeholder GM-mark until their kind's engine exists.
5. **Assign + run** — promote scope from UNASSIGNED → Personal / Group /
   Global (§7). The progress record is created; the player walks the DAG;
   runtime applies the frontier rules (§6).

### Promotion validation stays light

To reach **Plot**, an episode needs:

- `resting_conclusion` set (runtime requires it — §6), and
- either ≥ 1 outbound transition **or** an explicit "this is an ending" marker.

Nothing about siblings, parents, ordering, or reachability is validated.
Maturity leans forward in normal use but is **not a locked state machine** —
staff/owner can demote a node to rework it. The runtime soft-gate (§6) is the
real protection for players, not editor rigidity.

### The three views (almost entirely reusing existing surfaces)

- **Player** — never sees pitch text, internals, the notes ledger, or `risk`.
  Gets the visibility-filtered log (`serialize_story_log`), the status line
  (`compute_story_status_line`, extended for the deliberately-ambiguous
  WAITING_FOR_GM / RESTING copy), and the `resting_conclusion` at a rest.
  Tangents appear in the log as "what happened." It should *read like a
  story*, not a tracker.
- **GM** — `gm-queue` extended with aged WAITING_FOR_GM frontiers; the
  authoring editor for owned stories; full beat internals; the notes ledger
  (read + append).
- **Staff** — `staff-workload` extended with stale-frontier ages
  (dropped-ball detection); author/audit/demote/mark-`COMPLETED` on any
  story.

Frontend reshape is concentrated on the existing `StoryAuthorPage` /
dashboards: maturity controls, the new beat form (kind/advances/risk, with the
predicate config demoted to a Task/Requirement sub-config), the notes panel,
the `resting_conclusion` field, the UNASSIGNED scope, and the assignment
action — bolted on, not rebuilt.

---

## 6. The frontier — Waiting-for-GM vs. resting

The Episode DAG + Transitions remain the progression engine. The new rule:
**at each step, runtime consults the maturity of the node it is about to
enter.**

- **Next node is at Plot** → proceed normally via the existing
  `get_eligible_transitions` / `resolve_episode` path. Unchanged.
- **Next node exists but is Outline/Pitch, *or* there is no defined
  transition but an infant Chapter/Episode is seeded ahead** → progress enters
  a new pointer-level state **`WAITING_FOR_GM`** (a `StoryProgress` /
  `GroupStoryProgress` status, **not** a beat outcome). It pings
  `story.active_gms` via the existing narrative app and surfaces on the GM
  `gm-queue` and the staff `staff-workload` views **with age**, so a dropped
  ball (GM quit, swallowed by RL) is visibly stale and a senior GM/staffer can
  step in.
- **Nothing authored ahead at all — no transition, no infant content** →
  progress enters **`RESTING`**, *not* `COMPLETED`. The player simply
  experiences the current episode's written conclusion. The framing copy is
  **deliberately open-ended** — "the trail goes quiet here," never "the story
  is over, nothing more to do." Only an explicit staff/owner action sets
  `COMPLETED`.

This makes a **player-facing `resting_conclusion` a required authoring field
on every Episode** — distinct from the existing author-view
`summary`/`consequences` and from per-transition `connection_summary` (which
only shows when the story *does* advance through that edge). A resting point
has no chosen transition, so it needs its own text.

**A player is never hard-blocked from the rest of the game.** The story rests
at a clean episode boundary while normal RP and life continue (bite-sized, no
stuck state).

---

## 7. Scope and assignment

Add **`UNASSIGNED`** as the default fourth `StoryScope` value (keep
`CHARACTER` as the code value, "Personal" as the display label).

- **UNASSIGNED** — a story being authored that does not yet know who it is
  for. The creation default. Fully authorable (Pitch→Outline→Plot) but
  **cannot be run** — no progress record can be created — until promoted to a
  concrete scope. This lets a showrunner draft before deciding the story's
  audience.
- **Personal (CHARACTER)** — assign a `CharacterSheet`; creates
  `StoryProgress`. Existing path.
- **GROUP** — assign the GM table's people grouping, **optionally also a
  covenant**; creates `GroupStoryProgress` (keyed on `gm_table`, optional
  `covenant` association as a seam). Both groupings are valid: a freeform
  group grabbed for a story need not be a covenant and may become associated
  with one later.
- **GLOBAL** — singleton `GlobalStoryProgress`. Existing path.

**Scope is NOT trust-gated.** Bigger ≠ riskier. A starting GM can author a
Risk-0 Group or Global story (an all-lore public event with no stakes). The
**risk of the beats** is the only trust-gated envelope; a global story with
real consequences is gated automatically *through its high-risk beats*, not
because it is global.

**Assignment is GM/owner-driven**, with the player relationship established
through *existing* machinery — table membership, `StoryGMOffer`, sign-up —
not reinvented.

**Staff approval: the trust gate is the control.** No separate per-story
publish-approval workflow. A GM mechanically cannot exceed their envelope, so
shared-world protection is structural, not procedural. (A future
"request-to-exceed" escalation — a GM asking a senior GM/staff to sign off
when players do something unexpectedly high-risk mid-session — is noted as
skeleton, not built; see §10.)

---

## 8. Risk as a plain integer + the trust gate

No `RiskTier` model. Its every meaningful field (names, consequence
descriptors, reward bands) is deferred to when consequences are wired into
each subsystem, so a model now would be premature, near-empty structure.

- **`Beat.risk`** — `PositiveSmallIntegerField`, default `0`. Just a number.
  Semantic names, consequence meanings, and reward bands are assigned later
  (with the consequence work); the backbone only carries the number.
- **Future consequence/reward objects read `beat.risk` directly.** Each
  encodes its own "applies at risk ≥ N / forbidden above N" rule and checks
  the integer in place. No indirection.

### The authoring trust gate

The "which risk can this GM author" mapping cannot live on the beat. Since
both the risk→trust ladder *and* the GM earning curve are deferred, that
mapping collapses, for the proof-of-concept, to the only rule the PoC needs:

> **Staff → any risk. Non-staff (a "starting GM") → `risk` must be `0`.**

Enforced in the `Beat` serializer `validate()`. This is honest about what is
deferred — it invents no fake ladder — and it *is* exactly the PoC
requirement ("a starting GM authors and runs a story" = a Risk-0 story). When
GM leveling lands, the real "trust level N unlocks risk M" ladder replaces
that single check **with no schema change** — `risk` was an integer all
along.

When names/meanings are later assigned to the numbers, *that* is the moment
to decide whether `risk` becomes an `IntegerChoices` or grows a descriptor
model — decided then, with the consequence work, not now.

---

## 9. The story notes ledger

A per-Story **append-only notes ledger**, separate from the per-node pitch
text. Each entry carries:

- author (account/persona),
- OOC creation timestamp,
- body (general story notes and future-idea seeds).

Shown as an addendum so the next author knows what the last one was thinking.
**OOC / staff-and-GM only — never player-visible.** This is *not* a
promotable structure; entries do not become nodes. It is purely authorial
memory.

---

## 10. Sequenced follow-ups and the seams built now

The backbone runs end-to-end with every richer beat resolving via placeholder
GM-mark. Each follow-up is its own later brainstorm, in dependency order:

1. **Mission/Challenge engine** *(highest priority — the automated
   player→update loop with no GM online)*: the "player picks checks against
   their capabilities → branching outcomes" primitive. This *is* the
   codebase's existing Capabilities & Challenges surface (`resolve_challenge`).
   `TASK` beats resolved by it = Missions.
2. **Situation/Encounter resolution + Sessions**: GM-run live tooling — a GM
   running a session marks outcomes that feed transitions; Sessions are the
   container, tied to the existing `SessionRequest`/events bridge. Secondary,
   per "live tools after authoring tools."
3. **Consequence + reward computation**: objects that read `beat.risk` +
   outcome → legend/penalties. Where the risk *numbers get names and
   meaning*. Depends on (1)/(2) for outcomes to compute from.
4. **GM leveling / earning curve**: replaces the staff-any/non-staff-0 check
   with the real trust→risk ladder (no schema change). Carries the captured
   principle below, plus the request-to-exceed escalation and any per-category
   trust refinement.
5. **Covenant entity**: fills the optional group `covenant` seam when that
   post-MVP system lands.

### Seams built now (so the above slot in without reshaping)

- `Beat.kind`, `Beat.advances`, `Beat.risk` + the placeholder GM-mark
  resolution path on existing `BeatCompletion` / `Transition` machinery.
- `Episode.resting_conclusion`.
- `StoryProgress` / `GroupStoryProgress` `WAITING_FOR_GM` / `RESTING` states.
- Per-node `maturity` on Story / Chapter / Episode.
- Per-story notes ledger.
- `StoryScope.UNASSIGNED`.
- The single, swappable beat-save trust check.
- Optional nullable `covenant` association on group progress.

### Deferred skeleton — GM leveling and the XP principle

GM advancement is noted and skeletal; revisited after the backbone and the
resolution engines. Captured intent:

- Any player with positive trust can apply for Level 1 GM.
- **Baseline GM-XP:** running a session; a completed authored episode;
  volunteering for a GM-seeking player.
- **Large:** finishing a story to completion for a player/group.
- **Largest:** feedback from a player they have *not* GM'd for.
- **Minor:** *repeated* feedback from the same circle.

The design principle behind the curve — **reward breadth of service (new and
GM-orphaned players) over depth with the same friends** — is itself the point,
not just the numbers. The trust/feedback models already exist
(`PlayerTrust.gm_trust_level`, per-category `PlayerTrustLevel`,
`StoryFeedback`); the gating *hook* is built now, the *earning curve* is the
skeleton revisited later.

---

## 11. Decisions deferred (decide with the follow-up that needs them)

- Whether `risk` becomes an `IntegerChoices` or grows a descriptor model
  (decide with the consequence work).
- Per-category trust vs. single aggregate `gm_trust_level` for the real
  authoring ladder (decide with GM leveling).
- The request-to-exceed-tier escalation flow (decide with GM leveling).
- Covenant ↔ group-story association semantics (decide with the covenant
  entity).
- Pitch-prose storage: a dedicated `pitch` field per node vs. reusing
  `description`/`summary` — decide with the authoring-API follow-up
  (discovered follow-ups #6/#7). The half-built option (a `pitch` field with
  no API to write it and no maturity-visibility gate to enforce it) is
  intentionally **not** shipped now.

---

## Backbone implementation — discovered follow-ups (2026-05-16)

Items surfaced while implementing Tasks 1–10 of the backbone. Existing
sections above are unchanged; this records what shifted or was newly noticed.

1. **`compute_story_status_line` did not previously exist.** The plan and
   `docs/systems/stories.md` referred to it as an existing dashboards helper;
   it was actually *created* in this backbone (alongside the structured
   `compute_story_status`). Resolved — noted here for accuracy, and the
   systems doc has been corrected to reflect it as backbone-added.
2. **staff-workload + gm-queue scans are globally unbounded.** The new
   WAITING_FOR_GM surfacing in `GMQueueView` (`waiting_for_gm`) and
   `StaffWorkloadView` (`stories_waiting_for_gm`) mirrors the pre-existing,
   already-accepted MVP pattern of the stale-story and frontier scans (no
   pagination/caching). Bounding/caching all of these together is a future
   cleanup tracked with the existing stale/frontier scan cleanup, not a new
   regression introduced here.
3. **`_build_gm_queue_for_story` carries 6 list accumulators**
   (`# noqa: PLR0913`). Threading one list per queue section was the
   smallest additive change; collapsing the accumulators into an
   `@dataclass` is a clean, self-contained refactor best done as its own
   separate commit (no behavior change), deferred.
4. **Frontier "infant content ahead" is a story-wide heuristic.**
   `frontier._story_has_immature_content` treats *any* Episode in the story
   still below PLOT as "the author intends more" → WAITING_FOR_GM. A
   per-DAG-reachability refinement (only count episodes actually reachable
   from the current pointer) is deferred — reaffirming the existing design
   note, not a new decision.
5. **Null-target ("authoring frontier") transitions are left untouched by
   `_reconcile_status_after_advance`.** When `resolve_episode` advances to a
   `None` target, status reconciliation is intentionally skipped (a
   null-target transition is its own frontier concern). Out of scope for the
   backbone; documented follow-up.
6. **No product authoring API for the new fields (final holistic review,
   I-1).** `maturity`, `resting_conclusion`, and `is_ending` exist in
   models/services/tests but in **no serializer/view/url**;
   `promote_episode_maturity` (and Chapter/Story maturity promotion) have no
   endpoint; scope assignment has no cohesive create-progress API. The
   backbone delivers a correct runtime engine + seams that is runnable
   end-to-end **at the service layer**, but the success criterion's
   "staff/GM author + run a story" is reachable only via service functions,
   not through any interface. The authoring API + the §5 StoryAuthorPage
   reshape are a sequenced follow-up (own brainstorm). The engineering that
   shipped is sound and additive; this is a scope-honesty correction, not a
   defect.
7. **No pitch-text storage; no maturity-gated player visibility (final
   holistic review, I-2).** §4/§5 describe a per-node "pitch prose box" that
   is "never player-visible." Only the `StoryMaturity.PITCH` enum rung was
   built — there is **no `pitch` field** on Story/Chapter/Episode, and no
   serializer/`serialize_story_log` path suppresses a below-PLOT node's prose
   from players. (The runtime frontier structurally prevents players from
   *reaching* immature episodes, so there is no current data leak.) The pitch
   box + visibility gate are deferred and bundled with the authoring-API
   follow-up (#6).
