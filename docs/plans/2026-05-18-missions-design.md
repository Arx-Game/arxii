# Missions — Validated Design

**Status:** Core design validated via brainstorm (2026-05-18). Buildable whole.
Follow-up design passes are sequenced at the end; **authoring tooling is the
immediate next pass**, then in-progress persistence, then the rest.

**Context:** Missions are the framework doc's #1 sequenced follow-up
(`docs/plans/2026-05-15-stories-authoring-framework-design.md` §10) — "the
automated player→update loop with no GM online." They are the primary way
players affect the game world without staff oversight. This document is the
validated *engine* design; it deliberately stops at named seams for the
follow-up passes.

---

## 1. Purpose & design tenets

- **Standalone, general world-engagement.** A Mission is not "the inside of a
  Story beat." It is a standalone engine for engaging the world — solo, or as
  cooperative RP with friends/a covenant. A Story TASK beat can *optionally*
  point at a mission template as its resolver, but that is one extra output
  channel, not the mission's reason for being.
- **Emergent state, not pre-abstracted.** There is no neutral world-model
  behind a mission. The path *creates* the facts (go the home branch → the
  target is home; go the guild branch → he's at the office). No independent
  "where is the target" state exists.
- **Thin abstract text; player-authored narration.** The engine only ever
  verifies *capable + succeeded*. The *how* (minor flirting vs. a steamy
  night — mechanically identical) is the player's to narrate via a **Legend
  Entry**, explicitly unreliable-narrator, **never parsed for mechanics**
  (extends the existing "never read player prose for mechanics" rule).
- **No GM online, ever.** Staff/GM author templates; the engine runs
  everything.
- **Reusable / low-touch.** Most missions are infinitely reusable templates
  cycling on predicates with minor staff weighting.
- **Cooperative by construction.** Multi-person missions are friends/covenants
  opting in together. Disagreement-resolution modes are *coordination* tools,
  never PvP. Stays inside the cooperative-RP bedrock.
- **Risk always surfaced.** Players see Risk and Difficulty before committing;
  never a hidden gamble.
- **Structured consequences only.** All mechanical outcomes are structured
  effect primitives the engine applies; text is flavor.

---

## 2. Core structure: the mission graph

- A **Mission template** is an authored **graph of nodes**.
- A **node** presents a flat, additive **pick-list of options**.
- An **option** is exactly one of:
  - **Branch** — no check; routes to another node.
  - **Check** — a roll → routes by outcome tier (success/fail/botch); a tier's
    route may be a specific node *or* "pick one of N at random."
- **No engine arbitration.** Options are parallel choices; the *player picks
  one*; the pick (+ check result for a Check) deterministically routes. Two
  options being "contradictory" is irrelevant — exactly one is taken.
- A node mixes **challenge-container options** (e.g. "Distract", which expands
  into capability-derived sub-options) and **direct options** (e.g. a
  society-gated shortcut that skips ahead) as peers.

This maps onto the existing Challenge engine: `ChallengeTemplate` ≈ an
authored challenge, `ChallengeApproach` ≈ an option, `resolve_challenge`'s
unused `capability_source` param is the seam for capability-derived options.
Reuse `perform_check`, structured `Consequence`, `select_weighted`,
`filter_character_loss`, risk-transparency, `ResolutionType`.

---

## 3. Option sourcing (breadth + depth)

Two sources, **merged into one pick-list**:

- **Breadth — universal affordance-tagging.** A shared affordance taxonomy
  (e.g. `distraction`, `lethal`, `social-extraction`). **Any durable
  descriptor** can be tagged: capabilities, magic techniques, conditions,
  items, *and* distinctions, achievements, society/org standing. A challenge
  declares the affordances it accepts; the engine surfaces every
  affordance-matched descriptor the character owns as an option. Same unified
  registry shape already used for `mechanics.ModifierTarget`.
  - The `(descriptor → affordance)` **binding is a small reusable spec,
    authored once in the descriptor's home system, globally reused**:
    `produces: Branch | Check`, the check + base risk if Check, and the
    *thin abstract* IC framing line. Missions never re-author "what does a
    drinking contest roll" — that lives on the descriptor. (Active
    capabilities imply a check; passive descriptors like an achievement
    typically produce a Branch.)
- **Depth — authored special options.** Hand-placed options, each gated by a
  deterministic **predicate** over the acting character's durable state. Can
  be top-level peers or hung under a challenge. They appear as additional
  pick-list entries when their predicate holds (player still just picks one).

Missions may **accept/deny affordances** and override at the **authored-
special / per-predicate layer**, but do **not** locally retune a generic
affordance's base check. Hyper-specific exceptions live entirely in the
authored-special layer.

---

## 4. The shared predicate engine

- **Domain = the acting character's durable state only.** Capabilities,
  distinctions, achievements, society/org standing, conditions, threads,
  stats/skills. **No target sheet is ever read.** Missions are abstract w.r.t.
  targets — this is what keeps them infinitely reusable and GM-less.
- **Target-side uncertainty is folded into Check odds**, not predicates
  ("you're a famous singer" gates *visibility*; "is the faceless target a
  fan?" is just the author-tuned random factor inside that option's check).
- A *separate, non-mission* mechanism — a referenced check between two sheeted
  characters — is explicitly **out of scope** and possibly never used in
  missions.
- **One shared predicate evaluator, three call sites:** option visibility,
  affordance eligibility, mission availability. Reuse the
  `DistinctionPrerequisite.rule_json`-shape AND/OR/NOT evaluator; do not build
  three bespoke condition systems.

---

## 5. Risk vs Difficulty (two independent axes)

- **Difficulty** = the % odds given the character's capabilities (auto, from
  the chosen capability's own check vs the challenge severity). Pulling a
  woven Thread re-prices Difficulty live.
- **Risk** = the severity/likelihood of *bad* outcomes possible.
- Surfaced as **two distinct, color-coded fields** — never collapsed. An
  option can be low-risk/very-hard or high-risk/trivial, etc.

---

## 6. Riders

A capability/affordance can carry a **reusable typed consequence rider**
(e.g. "charmed witness", "detected as magic"), authored **once** on the
descriptor side as a structured `ConsequenceEffect` bundle. The mission
challenge has a per-challenge **allow/deny gate** for riders (a sealed room
denies "charmed witness"). When the option is taken and the rider is allowed,
it composes **additively** onto the won route's consequence. Not precedence —
just "taken option's effects = its route consequence + allowed riders."

---

## 7. State & evaluation model

- **No scratch variables.** Mission state = (current node) + (a durable-state
  snapshot taken **once at each node entry**) + (real consequences already
  written to the world — crime-watch entries, Resonance, reputation are real
  systems, not mission vars). "If you took the bribe" = "you are on the
  post-bribe node."
- **Evaluation cadence:** the option list is computed at node entry and is
  stable while the player sits there; re-querying on every browse is *not*
  done. Tanking your standing between node N and N+1 bites at the N+1 entry.

---

## 8. Front door — availability & the giver loop

- A **mission-giver** is an abstracted, unpiloted location/NPC (e.g. a Guild
  Hall guildmaster). Players browse, decline, or accept; accepted missions
  enter a personal quest-journal.
- Offering = the **shared predicate+weight engine** evaluated at the giver
  over (character durable state + world/org condition state + recent
  activity), drawing weighted-random N to display.
- **PC-weighted & player-tunable:** templates carry a **level/risk band**; the
  draw filters/weights to the PC's level; the player has a **risk-appetite
  dial** to stretch toward higher-risk/higher-reward — always informed.
- **Light world-state parameterization:** the chosen template's reward,
  cooldown, risk tier, or active option sub-pool may flex with world state.
  No procedural composition — strictly a weighted draw from authored
  templates.
- **Events = the same engine, perturbed.** A special event is an
  **Era/global-arc association + scope** on templates (reuses the existing
  `Era`/`advance_era` lifecycle, which owns "unwind → return to normal" for
  free). Activating an arc scoped to certain givers applies a **per-slot
  percent-replace** (staff-set, 0–100; 100 = guaranteed arc-only; replacement
  still respects the PC's eligibility/level/predicates — it draws that slot
  from the *arc-eligible* pool). Steady state = ambient (no-arc) templates.
- **Per-giver cooldown** after taking/completing, giver-configured
  (day/week/etc.).

---

## 9. Back door — completion, rewards, chaining

- A completed mission always emits a structured, **authoritative
  deed-record + applied structured consequences** (+ optionally a **chained
  mission**) (+ optionally a `BeatCompletion`/`Transition` signal **iff** the
  instance was launched as a Story TASK-beat resolver — `Beat.required_mission`).
- **Reward split:** immediate (money, collected on return to the giver) /
  **post-cron** (Legend Points, Resonance — batched via the `game_clock`
  scheduler) / **propagation** (rumors/news surfaced to predicate-scoped
  audiences: relevant orgs/societies and gossip-skilled PCs).
- **Legend Points** = the mechanical reward value. **Legend Entry** = the
  player-authored, unreliable narrative attached to the same deed-record.
  Same deed-record; one face is the engine ledger, the other the player's
  story. The mission engine's job ends at "emit the authoritative
  deed-record + apply structured consequences."

---

## 10. Multi-person missions

- **Cooperative by construction.** A receiver picks up a mission and **shares/
  invites** others into that run. The **participant set lives on the mission
  *instance*** — ephemeral, born and dies with the run. **No new persistent
  "group" entity; covenants are not overloaded.** A formal group-signup is a
  strictly-later add-on only if ad-hoc sharing proves insufficient (YAGNI).
- The **receiver = contract anchor / contract-holder.**
- At a node, the option list is the **union of all participants' eligible
  options**, each tagged with which participant can perform it.
- **Conflict-resolution mode is authored per decision point:** `coinflip` |
  `vote` | `joint-simultaneous`. `joint-simultaneous` also carries an authored
  **combine rule**: any-success / all-must-succeed / count ≥ K.
- **JOINT routing — combined success/failure bucket, not per rolled tier:**
  a JOINT node routes by the COMBINED success/failure bucket (best
  success-tier route / worst failure-tier route via `CheckOutcome.success_level`),
  NOT per rolled tier. Authors of JOINT contract-holder options must
  therefore author at least one success-tier route AND at least one
  failure-tier route on the holder pick; the specific tier within each
  bucket selects the representative consequence/destination.
- **Moral/karmic consequence follows the actor** (the killer takes the
  abyssal Resonance and the signature notoriety; the lookout gets accomplice
  flavor). A party cannot launder a deed by choosing who acts — complicity
  and direct action are deliberately different.
- **Terminal mission reward is distributed by an author-chosen group rule**
  (all-equal / by-role / by-participation).
- **Contractual consequence is the contract-holder's alone**: the giver
  cooldown, the giver-reputation/standing delta, and the giver's
  failure-anger. Helpers get their own per-act Resonance/Legend and a
  terminal-reward share, but don't build/burn giver standing and aren't
  cooldowned. This deliberately enables a covenant designating a "contract
  runner" who funnels guild work — **intended RP, not an exploit.**

---

## 11. Terminology (use consistently)

- **Mission template** (authored, reusable) vs **mission instance** (a single
  run; owns the participant set + graph position).
- **Affordance** (shared tag vocabulary) ; **durable descriptor** (anything
  taggable: capability/distinction/achievement/standing/condition/thread/
  item).
- **Deed-record** (authoritative structured output of a run).
- **Legend Points** (mechanical reward) vs **Legend Entry** (player narrative).
- **Contract-holder** (the receiver/anchor of a multi-person run).

---

## 12. Reuses / integration points

- **Challenge engine** (`mechanics`): `ChallengeTemplate`/`ChallengeApproach`/
  `resolve_challenge` (+ `capability_source` seam), structured `Consequence`,
  `select_weighted`, `filter_character_loss`, `ResolutionType`.
- **Stories DAG**: `Beat.required_mission`, `BeatCompletion`, `Transition`,
  TASK beats (optional resolver channel only).
- **Era / global arcs**: availability perturbation + free unwind lifecycle.
- **Predicate engine**: `DistinctionPrerequisite.rule_json`-shape evaluator.
- **Resonance / Legend Points / reputation / crime-watch**: real consequence
  systems the engine writes to (not mission vars).
- **game_clock scheduler**: post-cron reward application batch.
- Distinctions, achievements, conditions, threads, society standing: durable
  descriptors that affordance-tag and/or feed predicates.

---

## 13. Sequenced follow-up design passes (ordered)

1. **Authoring tooling (IMMEDIATE NEXT PASS).** The staff/GM editor for the
   whole graph: nodes; options (direct vs challenge-container); accepted
   affordances; authored-special options + predicates; riders allow/deny;
   bookend lore (rich) vs thin per-option text; outcome→reward/penalty
   seeding; level/risk band; Era/arc association + scope + percent-replace;
   per-node conflict-resolution mode; multi-person settings. Load-bearing —
   nothing else can be authored or tested without it; standing position is
   that authoring tools matter more than live tools.
2. **In-progress persistence.** A mission instance spans multiple grid rooms,
   instanced temp rooms, and real time. Persist / abandon / resume / expiry
   of a live instance; the quest-journal surface. **Make-or-break** —
   multi-room missions are dead without it. Presupposes (1) so multi-room
   missions can be authored at all. Must respect "no persistent stuck states
   that block normal RP/life between sessions."
3. **The rest:**
   - **Mission chaining lifecycle** — capture → prison-escape: is a chain
     *forced*, offered, or opt-in? Collides directly with the "no stuck
     states between sessions / bite-sized" principle; needs a careful ruling.
   - **Reward application + rumor/news propagation** — the post-cron batch,
     and the audience model for who hears (org/society/gossip-skill
     predicate-scoped). **RESONANCE sink resolved by #1737** (real
     `_grant_resonance()`, `GainSource.MISSION_REWARD`); LEGEND_POINTS and the
     rumor/news audience model remain open. **Separately, #1753 found a bigger,
     more fundamental gap:** `apply_deed_rewards` — the function that actually
     routes emitted reward lines into the payout queue — has zero production
     callers anywhere in the missions engine (only test suites call it). This
     affects every reward sink, not just RESONANCE, and means #1737's plumbing
     is correct but does not yet pay out in live gameplay until #1753 wires the
     emission→apply routing seam to the real resolution engine.
   - **Grid routing & instancing** — spawn/teardown of instanced temp rooms
     (target's home/office), admission = the instance participant set, vs.
     the emergent-not-pre-abstracted tenet.
   - **Character signature / calling-card** — a per-character authored
     signature (e.g. green-lipstick mark) usable as a terminal option/rider.

---

## 14. Explicitly NOT decided (do not assume in future sessions)

- Everything in §13.3 is open.
- The authoring tooling UX/data-model (§13.1) is unstarted.
- Persistence/abandon/expiry semantics (§13.2) are unstarted.
- Whether a chained mission is forced/offered/opt-in (§13.3) — open, with a
  known tension against the no-stuck-states principle.
- The rumor/news audience predicate model (§13.3) — open.
- Instanced-room lifecycle/admission specifics (§13.3) — open.

The §1–§12 engine architecture is validated and stable; build against it.
