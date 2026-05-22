# Challenge ↔ Missions Integration — Findings & Gap Analysis

**Status:** Investigation findings. Prepared overnight 2026-05-22 to ground the
challenge↔missions integration design conversation, which is a prerequisite for the
mission-authoring implementation plan (see
`docs/plans/2026-05-22-mission-authoring-tooling-design.md` §8.4).

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

## 4. Reconciliation questions for the morning

**Q1 — The two capability systems (Divergence 1).** Do `Affordance`/`AffordanceBinding`
and `Application`/`CapabilityType` get unified, or coexist?
- *Option A — coexist.* A mission node surfaces options from both: affordance-bindings
  *and* a referenced challenge's `Application`-keyed approaches. Least work; two systems
  forever.
- *Option B — converge.* Treat `Application` as one *kind* of affordance binding, or
  re-express `ChallengeApproach` eligibility in affordance terms. Big, but kills the
  duplication.
- *Option C — challenge approaches define their own affordance bindings.* When a challenge
  is authored, each approach's `(CapabilityType, Property)` is *also* registered as an
  `AffordanceBinding`, so at runtime missions only ever see affordances.

**Q2 — Data-source vs engine (Divergence 4).** Confirm integration shape (a): a node
consumes a `ChallengeTemplate` as authored data (its approaches → options), and missions
resolve through `resolve_option`. Recommended in §5.

**Q3 — Auto-success (Divergence 3.3 / 3.4).** Degenerate always-succeed `CheckType`, a
missions-side auto-success flag on the option, or a new field on `ChallengeApproach`?

**Q4 — Which challenge semantics ride along (Divergence 3).** `severity` → mission check
difficulty seems right. `challenge_type`, `discovery_type`, `blocked_capability`,
`properties` — ignored in a missions context, or meaningful? Likely ignored; confirm.

**Q5 — Missions vs situations (Divergence 5).** What is the long-term relationship? Plausible
framings: missions = the authored branching *narrative* graph (staff content); challenges
= reusable *obstacle definitions* a mission node pulls in; situations = a GM-facing
ad-hoc *placement* layer that may itself just consume challenges, OR may be superseded by
missions over time. This question is bigger than authoring tooling and may deserve its own
note — but the authoring implementation plan should not pretend it doesn't exist.

---

## 5. Recommendation (a starting position, not a decision)

- **Integration shape: data-source (Q2 → option a).** A mission node references a
  `ChallengeTemplate`; the engine reads its `approaches` and expands them into node
  options; resolution stays entirely within `resolve_option`. `resolve_challenge`,
  `ChallengeInstance`, `CharacterChallengeRecord` are untouched by missions. This matches
  §8.4, avoids a parallel record lifecycle, and keeps the `CharacterEngagement` model
  honest (a character on a mission stays `engagement_type=MISSION`).
- **Capability systems: lean toward Q1 option C** — challenge approaches register
  affordance bindings — so missions only ever resolve options through one eligibility
  system (`Affordance`). This contains the blast radius without a full convergence
  project. Needs validation that `Application`'s `(capability, property)` eligibility can
  be faithfully expressed as an affordance binding.
- **Auto-success: a missions-side flag** on the approach-option, not a degenerate
  `CheckType` (which would pollute the check catalogue) and not a `ChallengeApproach`
  field (which would couple a missions concern into the challenge model).
- **Challenge semantics: `severity` → difficulty; everything else ignored** in a missions
  context until proven otherwise.
- **Missions vs situations (Q5):** explicitly out of scope for the authoring
  implementation plan — but record it as a known open architectural question, because it
  determines whether effort later goes into situations at all.

This is a **starting position for discussion**, deliberately conservative (reuse challenge
*data*, change neither engine). The morning conversation should pressure-test it,
especially Q1 and Q5.

---

## 6. Suggested sequencing after the morning conversation

1. **Settle Q1–Q5** in a short design conversation (this doc is its input).
2. Fold the resolution into the authoring design doc's §8.4 and §11.9, replacing the
   "recorded as open" placeholder.
3. *Then* write the mission-authoring implementation plan (`superpowers:writing-plans`) —
   with the challenge-integration piece now concrete rather than a TBD.

Nothing in the rest of the authoring design (the working-draft/publish model, the giver,
the predicate builder, the canvas, browse/search, copy, the testing loop, §11 extensions
1–8 and 10) depends on Q1–Q5 — that ~85% of the plan is writable regardless. Only the
check-source picker and the node-attached-challenge surface wait on this.
