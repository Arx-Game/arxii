# Challenge ↔ Missions Integration — Findings & Gap Analysis

**Status:** Investigation findings + resolution. Prepared overnight 2026-05-22; the
reconciliation questions were discussed and decided the same day — see §4. **All five
(Q1–Q5) resolved.** The challenge↔missions integration is fully designed; the
mission-authoring implementation plan can now be written. The authoring design doc
(`docs/plans/2026-05-22-mission-authoring-tooling-design.md`) §8.4 / §11.9–10 / §12 has
been updated to match the §4 resolutions.

**Purpose:** The authoring design folded in "a mission node's CHECK option can reference a
`Challenge` instead of a bare `CheckType`, and the challenge's capability-keyed approaches
expand into node options." That assumed a clean fit with the existing challenge system.
This document reports what the challenge system *actually* is, where the fit is clean, and
where it is not — with reconciliation options for each gap. It makes no decisions.

**Confidence:** Based on a direct read of `world/mechanics/models.py` (challenge/situation
models), `world/mechanics/challenge_resolution.py`, `world/mechanics/constants.py`,
`world/mechanics/engagement.py`. NOT deep-read: the situation *services*, the `actions`
app `ActionTemplate` pipeline, and the `mechanics` view/serializer layer. Items depending
on those are flagged "needs a closer look."

---

## 1. The challenge / situation system as it exists today

It lives in `world.mechanics` (not its own app). It is a **GM-facing scenario system**,
sibling to combat and to missions.

### 1.1 `ChallengeTemplate`

A reusable blueprint for a Challenge — "what Properties the challenge has, how severe it
is, what approaches resolve it, what consequences follow."

- `name`, `description_template` (with `{variables}`)
- `category` FK → `ChallengeCategory`
- `severity` (PositiveInteger) — **this is the difficulty**; `resolve_challenge` passes it
  as `perform_check(..., target_difficulty=template.severity)`
- `challenge_type` — `INHIBITOR` (blocks actions/progress) | `THREAT` (actively causes harm)
- `discovery_type` — `OBVIOUS` (visible if capability met) | `DISCOVERABLE` (must be learned)
- `blocked_capability` FK → `conditions.CapabilityType`
- `properties` M2M → `Property` (through `ChallengeTemplateProperty`)
- `consequences` M2M → `checks.Consequence` (through `ChallengeTemplateConsequence`, which
  also carries `resolution_type` + `resolution_duration_rounds`)
- `approaches` reverse-relation → `ChallengeApproach`

### 1.2 `ChallengeApproach` + `Application` — the capability-keyed approach

**This is the model the missions-authoring design wants to lean on.**

`ChallengeApproach` — "A way to resolve a Challenge, linking an Application to a check
type. This is where the system connects *what you can do* (Application) with *how to
resolve it* (CheckType)."

- `challenge_template` FK
- `application` FK → `Application`
- `check_type` FK → `checks.CheckType`
- `required_effect_property` FK → `Property` (nullable)
- `display_name`, `custom_description`
- `action_template` FK → `actions.ActionTemplate` (nullable) — when set, resolution routes
  through the `actions` pipeline instead of a plain check
- Unique per `(challenge_template, application)`

`Application` — "Pure eligibility record: Capability + Property = *you can attempt this*."

- `capability` FK → `conditions.CapabilityType`
- `target_property` FK → `Property`
- `required_effect_property` FK → `Property` (nullable)
- Applications carry **no** check type, narrative, or difficulty — "those come from the
  delivery mechanism and the Situation."

So an approach = `(Application, CheckType)`, and an `Application` = `(CapabilityType,
Property)` eligibility. The capability primitive is **`conditions.CapabilityType`**.

`ApproachConsequence` — per-approach consequence overrides (when an approach's outcomes
differ from the template-level set).

### 1.3 Situations — a scenario layer above challenges

- `SituationTemplate` — "A reusable collection of Challenges that form a coherent
  scenario. GMs place Situations; the system generates player options automatically based
  on the Challenges' Properties and the characters' Capabilities."
- `SituationChallengeLink` — through-table with `display_order` **and `depends_on`
  (self-FK)** — i.e. challenges within a situation form a *dependency graph*.
- `SituationInstance` — a live situation at a `location` (ObjectDB), `template_variables`
  JSONField, optional `scene` FK, `created_by`.
- `ChallengeInstance` — a live challenge at a `location`, optional `situation_instance`
  FK, a `target_object` ("the object embodying this challenge in the world"), `is_active`,
  `is_revealed`.
- `CharacterChallengeRecord` — a character's resolution: `character`, `challenge_instance`,
  `approach`, `outcome` FK → **`traits.CheckOutcome`**, `consequence` FK → `checks.Consequence`.

### 1.4 `resolve_challenge` — the resolution flow

`resolve_challenge(character, challenge_instance, approach, capability_source)`:

1. Validate (`is_active`, `is_revealed`, not already resolved, approach belongs to template).
2. If the approach has an `action_template`, route through `actions.start_action_resolution`.
   Otherwise: `perform_check(character, approach.check_type, target_difficulty=template.severity)`.
3. `_select_consequence(approach, template, check_result.outcome, character)` — approach-level
   consequences override template-level for the matching `outcome_tier`; weighted pick via
   `select_weighted`; `filter_character_loss`; **synthetic unsaved `Consequence` fallback**
   when no tier matches.
4. `apply_resolution(PendingResolution(check_result, consequence), context)`.
5. Update challenge state (`DESTROY` → deactivate the instance).
6. Create a `CharacterChallengeRecord` carrying `outcome` (a `CheckOutcome`).
7. Return a `ChallengeResolutionResult`.

### 1.5 `CharacterEngagement` — the sibling-systems signal

`world/mechanics/engagement.py`: `CharacterEngagement` is a OneToOne on a character — "a
character can be engaged in at most one stakes-bearing activity." `engagement_type` ∈
**{CHALLENGE, COMBAT, MISSION}**, `source` is a GenericForeignKey to the engagement
source.

The codebase already models challenge / combat / mission as **three parallel engagement
types**, unified only by this "what are you currently doing" pointer (plus transient
process modifiers). Missions and challenges are *intentionally* separate systems — not
nested, not one-built-on-the-other.

---

## 2. What the mission-authoring design (§8.4) assumes

- A mission CHECK option's check-source is either an inline `CheckType` or a referenced
  `Challenge`.
- A challenge = a set of **capability-keyed approaches** + a **universal default
  approach**, each resolving to the standard `CheckOutcome` ladder.
- Attaching a challenge to a node **populates the node with approach-options** — one per
  approach the character qualifies for, the default always included.
- Each approach-option resolves and routes on the shared outcome ladder "exactly like any
  check." No special challenge→outcome bridge; approaches simply *are* options.

---

## 3. Gap analysis

### 3.1 Clean matches — the fit is real

- **Same outcome currency.** `resolve_challenge` produces `check_result.outcome`, a
  `traits.CheckOutcome`; `CharacterChallengeRecord.outcome` stores it. Missions route on
  `CheckOutcome` tiers. The "challenge→outcome bridge" the authoring design flagged as an
  open question **is trivial — it already exists.**
- **Same resolution primitives.** Challenge resolution and missions resolution both use
  `perform_check`, `apply_resolution`, `select_weighted`, `filter_character_loss`,
  `Consequence` keyed by `outcome_tier`, and the *identical* synthetic-unsaved-`Consequence`
  fallback. Missions Phase 3 explicitly mirrored `_select_consequence`. They are parallel
  implementations of one shape.
- **`ChallengeApproach` genuinely IS a capability-keyed approach.** `(Application,
  CheckType)` — eligibility + roll — is exactly the structure §8.4 wants.

### 3.2 Divergence 1 — two different capability/eligibility systems

This is the biggest one. There are **two unrelated answers to "what can this character do
here":**

- **Missions:** `Affordance` + `AffordanceBinding` — a universal tag on any durable
  descriptor (capability, distinction, achievement, condition, thread, item…), bound once
  in the descriptor's home system; `bindings_for_character` surfaces a character's
  affordance-options.
- **Challenges:** `Application` = `(conditions.CapabilityType, Property)` eligibility;
  `ChallengeApproach` keys on `Application`.

A challenge's approaches key on `Application`/`CapabilityType`. A mission node's
affordance-options key on `Affordance`. "Attach a challenge to a node and its approaches
become options" therefore means the node surfaces options from *two different eligibility
systems at once* — unless the systems are reconciled.

### 3.3 Divergence 2 — no auto-success in `ChallengeApproach`

Every `ChallengeApproach` is `(Application, CheckType)` — always a roll. The design's
"can fly → Fly out → auto-success" has **no model representation**. Options: a degenerate
always-succeed `CheckType`; a missions-layer auto-success flag; or a model addition.

### 3.4 Divergence 3 — challenges carry semantics missions said they didn't want

`ChallengeTemplate` carries `severity`, `challenge_type` (INHIBITOR/THREAT),
`discovery_type` (OBVIOUS/DISCOVERABLE), `blocked_capability`, `properties`. The missions
implementation's confirmed decision was to *not* take on these combat/situation/reveal
semantics. Referencing a challenge for its approaches means deciding which of these ride
along and which are ignored in a missions context (e.g., does a node-referenced challenge's
`discovery_type` mean anything? its `severity` as the difficulty — yes, plausibly; its
`THREAT` type — unclear).

### 3.5 Divergence 4 — `resolve_challenge` is a self-contained engine, not a library call

`resolve_challenge` validates a **`ChallengeInstance`**, performs the check, applies
consequences, **creates a `CharacterChallengeRecord`**, deactivates the instance. Missions
have their *own* resolution (`resolve_option`) that creates `MissionDeedRecord`, snapshots
nodes, routes the graph.

If a mission node "uses a challenge," there are two integration shapes:

- **(a) Data-source.** A mission node reads a `ChallengeTemplate`'s *approaches* purely as
  a source of options. Missions resolve those options through `resolve_option` as normal.
  `resolve_challenge`, `ChallengeInstance`, `CharacterChallengeRecord` are **not used** in
  a missions context. `ChallengeTemplate`/`ChallengeApproach` are consumed as authored
  *data*, not run as an *engine*.
- **(b) Engine call.** A mission node, on resolution, calls `resolve_challenge` — which
  needs a `ChallengeInstance` and produces a `CharacterChallengeRecord` parallel to the
  `MissionDeedRecord`.

§8.4's framing ("approaches simply *are* options; each resolves like any check") strongly
implies **(a)**. (a) is also far cleaner — no parallel instance/record lifecycle, no
double bookkeeping. But (a) means `ChallengeApproach`'s `action_template` path and
`ApproachConsequence` overrides are either reused by the missions resolver or ignored.

### 3.6 Divergence 5 — situations are already a scenario graph

`SituationTemplate` is "a reusable collection of Challenges forming a coherent scenario,"
and `SituationChallengeLink.depends_on` makes the challenges within it a **dependency
graph**, with options auto-generated from capabilities. That is conceptually a
*scenario-graph engine* — the same broad shape as the missions engine (a graph of nodes,
options auto-surfaced from capability/affordance).

So the duplication is not only at the check level; there is overlap at the **scenario
level**. The integration needs an explicit ownership story: what is a *mission* for, what
is a *situation* for, and do they coexist permanently or does one subsume the other.

---

## 4. Reconciliation questions — and their resolution

Discussed and decided 2026-05-22. **All five resolved.**

**Q1 — The two capability systems (Divergence 1). → RESOLVED: retire affordances.**
The investigation found this is *accidental duplication*, not two valid concerns:
`Affordance`'s own docstring describes serving "a mission challenge"; both systems do the
identical capability→option job; both resolve identically. The missions `Affordance` /
`AffordanceBinding` system was a missions-local reinvention built while missions were
decoupled from `mechanics.ChallengeTemplate`.
**Decision:** retire `Affordance` / `AffordanceBinding` / `bindings_for_character` / the
resolver dispatch. A mission node's options come from exactly two sources — **authored
options** (hand-placed, optionally predicate-gated via the §7 requirements builder) and
**challenge-contributed options** (from attached `ChallengeTemplate`s). The one thing
affordances did that this loses — an option auto-surfacing from a *non-capability*
descriptor (achievement/distinction/condition) — is recovered as an *authored option with
a predicate gate*, so nothing wanted is lost. (A separately-noted future enhancement:
modelling achievement/reputation/affection as *derived social capabilities* so social
challenges can key approaches on them — a capability-system change, not authoring.)

**Q2 — Data-source vs engine (Divergence 4). → RESOLVED: data-source.**
A mission node *references* a `ChallengeTemplate` and consumes its approaches as authored
data — the options' existence, capability gates, and check types. Mission resolution stays
entirely within `resolve_option`; `resolve_challenge` / `ChallengeInstance` /
`CharacterChallengeRecord` are not invoked by missions. Everything downstream of the
outcome (routes, consequences, rewards, flavor) is mission-authored. A character on a
mission stays `engagement_type = MISSION`.

**Q3 — Auto-success (Divergence 3.3 / 3.4). → RESOLVED: a `ChallengeApproach` field.**
Auto-success is a genuine *challenge-system* concept — some capabilities simply trivialize
an obstacle ("fly out of the pit"), and the challenge author is the one who knows that.
`ChallengeApproach` gains an `auto_succeeds` boolean. An auto-success approach surfaces as
an option that skips the roll and lands in the top outcome tier. This is a small,
legitimate addition to the challenge model (challenges want it in their own right; missions
just benefit) — *not* a degenerate `CheckType` (which would pollute the check catalogue)
and *not* a missions-only flag (which would put the concept in the wrong layer).

**Q4 — Which challenge semantics ride along (Divergence 3). → RESOLVED.** `severity` →
the mission check difficulty for the approach rolls. `challenge_type`, `discovery_type`,
`blocked_capability`, `properties` → **ignored in a missions context.** Rationale: a
mission node that presents a challenge has, by presenting it, already made it obvious —
every challenge used inside a mission is effectively the OBVIOUS discovery type, so
`discovery_type` is moot; framing, reveal, and routing are mission-owned, so the rest do
not apply.

**Q5 — Missions vs situations (Divergence 5). → RESOLVED (in principle): coexist.**
Missions, combat, and challenges are sibling engagement types (`CharacterEngagement`
already models this). Missions are the authored branching *narrative* graph (staff
content); `Challenge`s are reusable *obstacle definitions* both missions and GM Situations
pull in. Missions and Situations coexist as parallel scenario tooling, both consuming
challenges. Whether that stays permanent is a broader architectural question, recorded but
out of scope for the authoring implementation plan.

---

## 5. Recommendation — superseded by the §4 resolutions

This section was the pre-discussion starting position. Where the §4 discussion landed
relative to it:

- **Q2 (data-source) and Q5 (coexist)** — adopted as recommended.
- **Q1** — diverged *further* than recommended: rather than the conservative "challenge
  approaches register affordance bindings" (which would have kept the `Affordance` model
  alive), the decision was to **retire the `Affordance` system outright**, the
  investigation having shown it to be accidental duplication.
- **Q3** — diverged: the recommendation was a missions-side flag; the decision was a
  `ChallengeApproach.auto_succeeds` field, on the grounds that auto-success is a real
  challenge-system concept the challenge author owns, not a missions-layer concern.
- **Q4** — adopted as recommended: `severity` → difficulty, the rest ignored in-mission.

See §4 for the authoritative final decisions.

---

## 6. Remaining sequencing

Q1–Q5 are all settled (§4); the authoring design doc is updated to match. The next step is
to write the mission-authoring implementation plan (`superpowers:writing-plans`) — the
challenge↔missions integration is now a concrete data-source design with no open
architectural questions.
