# Mission Authoring Tooling — Design

**Status:** Validated design (brainstormed 2026-05-22). Not yet an implementation plan.

**Goal:** A staff-facing tool — "Mission Studio" — for authoring the mission content the
merged missions engine can only otherwise be fed by hand-written ORM calls. Authoring
tooling is the #1 sequenced follow-up to the missions core; nothing is playtestable
without it.

**Scope of this document:** the authoring *tool* — surfaces, workflows, and the engine
model extensions the tool requires. It does not design the missions engine (merged), the
node→room binding (follow-up #2), or the sibling staff creation tools.

---

## 1. Context

The missions **engine** is merged: the graph model (`MissionTemplate` → `MissionNode` →
`MissionOption` → `MissionOptionRoute` → rewards), the resolution engine, multi-person
orchestration, the front/back door. (The merged Phase 1 `Affordance` / `AffordanceBinding`
system is being **retired** — see §8.4 and §11.9.) What does not exist is any way to
*build* a mission — a graph today could only be constructed by hand-writing Django ORM
calls.

Mission Studio fills that gap. It is a React tool on the staff frontend, backed by a DRF
API over the missions models (extended where the authoring vision requires — see §11).

---

## 2. Cross-cutting principles

These shape every section.

**Solo trusted author — no abuse-case scaffolding.** The tool is for one person: staff
(the project owner). No permission tiers, no review/approval workflow, no abuse
mitigation. A future GM-facing layer is explicitly *not* designed now; if it ever comes,
it wraps this tool, it does not reshape it. Draft/publish (§4) is a *workflow* state, not
a safeguard.

**Mission Studio is one tool in a staff creation suite.** Sibling tools — a challenge
creator, room creator, item creator, NPC creator — are out of scope here, but Mission
Studio is built to be a good citizen of the suite:

- It lives in a shared staff-frontend shell with shared navigation.
- Anywhere it *references* an entity another tool owns (a challenge now; rooms / items /
  NPCs for the giver later), the picker follows one pattern: **pick existing · create
  new (hop to the sibling tool, return) · jump to edit.**
- That picker is a reusable component, not a missions-special. The sibling tools inherit
  the convention.

**Fast skeleton, fresh skin.** The tool optimises for reproducing *mechanical structure*
cheaply while keeping *narrative prose* conspicuously the author's to write. Arx's heart
is roleplay; automation is tolerable only while the result still reads as an immersive
story. Reuse never silently produces same-y content (§8).

**Replayability is a first-class goal.** Randomisation — weighted random outcome pools —
is built to be cheap to author, so a re-run mission genuinely diverges (§7).

---

## 3. Shape & scope

**What it is:** a staff-only authoring tool. Its heart is a visual graph editor — a
canvas of mission nodes you place, drag, and connect — with a drill-down into node and
option detail.

**What it is *not*, for MVP:**

- **No in-tool simulator.** Testing is done by playing the mission in-game with a staff
  persona (§9). The tool provides the staff *powers* to do that; it does not replicate
  the resolution engine in the browser.
- **No node→room binding.** Nodes stay abstract. Threading a mission physically through
  the grid — the Vyper "go to the guild hall, enter the instanced room" layer — is the
  in-progress-persistence follow-up. It is *required for go-live* but sequenced after
  authoring. Mission Studio will later grow a node-location field; not in MVP.
- **No GM access, no multi-author concerns.**

---

## 4. The working-draft / publish model

Every mission is a graph: a `MissionTemplate` with its nodes, options, routes, rewards.
A mission has two postures:

- **Draft** — being built or edited. Never offered in-game through a giver. This is what
  the editor always operates on.
- **Live** — a published version players receive through givers.

**A brand-new mission** is draft-only — it has no live version, so the game does not see
it. Build, publish, and the first live version comes into being.

**Editing a published mission:** opening it gives you a **draft copy** to work on — a
separate working graph. The live version keeps serving new instances, unchanged, the
entire time you edit. You make a coherent batch of changes — touch the ending node, the
dozen nodes beneath it, add new options — all in the draft, invisible to the game. On
**publish**, the whole batch replaces the live version **atomically**: there is never a
moment where a player can pick up a half-edited graph.

Editing is a **session** with a defined start and end, not a keystroke stream. "Edits go
live" happens at publish, not on the first keystroke.

**In-flight instances** are pinned to the version they were born on; edits and
re-publishes never reach a player who is mid-mission. The engine's per-node
`MissionNodeSnapshot` already guarantees this at the node level; pinning the instance to
its version makes it total.

**"New draft mission" and "editing a live mission" are the same mechanism** — a working
draft that goes live on publish. The only difference is whether a published version
already exists underneath to keep serving meanwhile.

*Implementation fork (for the implementation plan, not decided here):* the working draft
may be a full working-copy fork promoted on publish, or a thin revision model. The
*behaviour* above is the design.

---

## 5. Browse, search & the mission detail panel

Mission Studio opens on a **browser** — the list the author lives in between sessions.
Rows show name, status (`Draft` / `Live` / `Live · editing`), level band, category,
risk, starter area. Per-row actions: open, copy, delete. The browser is also where
*create new* and *copy* (§8) start.

**Selecting a mission** (without opening the editor) expands a **detail panel** — a live
footprint of that mission, all read from existing instance/deed data, no new storage:

- **Lifetime completions** — a count; click it for each run: who played it, and the
  outcome reached.
- **Active instances** — count of in-progress, non-abandoned runs, each showing the node
  it currently sits on. The "is anyone stuck?" early-warning view.

**Search facets**, two tiers:

- *Available at MVP* (data exists today): name, level band, area (giver → room →
  `Area`), category (new `MissionCategory` lookup, multi-select — §11), risk
  (`risk_tier`), org/society (via `giver.org`), status.
- *Reward-content facets*: "rewards Legend Points / money / an item" as a query over
  `MissionOptionRouteReward.sink` — works at sink granularity at MVP.
- *Deferred facets*: filtering by **resonance type** or **legend range** waits on the
  reward-payload-enrichment follow-up (rewards do not yet carry a typed resonance or a
  range-queryable amount). The facet bar is built to grow; these slot in later.

---

## 6. The giver

Givers are the most significant engine extension. Today `MissionGiver` is thin: `name`,
one `location` FK, `org`, a flat `templates` M2M.

**Givers are shared world fixtures.** A giver — the Smiling Shadows guildmaster — is
authored *once* as a thing that exists in a room; missions *attach* to it; one giver
surfaces many missions. The engine's existing `templates` M2M already assumes this.
Mission Studio gets a small **giver library** alongside the mission browser; authoring a
mission includes "attach to giver(s)."

**A giver is a room + a giving mechanism**, and the mechanism has three kinds, modelled
with the project's `DiscriminatorMixin` (a `giver_kind` field selecting which FK
matters):

- **NPC** — an abstract giver NPC the player talks to. Not piloted, not a sheet.
- **Environmental detail** — an examinable thing in the room (a real item *or* a room
  detail): a poster, a bloodstain, an odd symbol. The MMO-quest-starter pattern: noticing
  it kicks off the chain.
- **Room trigger** — no object at all; entering the room rolls the offer. Ambient
  "living world" discovery.

**Giver standing.** An abstract NPC giver, though not a sheet, can hold a per-player
**standing** (affection / reputation). Missions gate on it ("enough affection with the
guildmaster"). This is a new per-(giver, character) model — generalising the existing
`MissionGiverCooldown` to also hold a standing value — and a new predicate leaf
(`giver_standing_at_least`, §7) so requirements can reference it. The **mechanic that
moves standing** — flirt/seduce checks against the NPC — is adjacent gameplay work,
flagged as a dependency, *not designed here*.

**Giver ↔ mission link** becomes a light through-model: odds (draw weight) and
requirements default to the mission template's own values, with optional per-link
override for "same mission, two givers, different odds."

---

## 7. Requirements & the predicate builder

Mission availability supports arbitrarily nested **any/all conditionals** — and the
engine already has the framework: Phase 0's shared predicate evaluator. `availability_rule`
is not a flat list, it is an AND/OR/NOT predicate tree (the `DistinctionPrerequisite.rule_json`
shape). The tooling is a *UI over a data shape that already exists*.

The **requirements builder** is a visual predicate-tree editor: AND / OR / NOT grouping
nodes, leaf conditions at the bottom. It is **reused in two places**:

1. **Giver/mission availability** — the gate on whether a mission is offered at all.
2. **Authored-option gates** — an authored option inside a node carries the same kind of
   tree deciding whether it shows for a given character.

**The leaf palette** is driven by the engine's predicate **leaf-resolver registry**. The
builder offers exactly the leaf types with a registered resolver. Target vocabulary:
character level, org membership, society/org reputation tier, achievement held, codex
entry unlocked, resonance type held, giver standing, condition held, distinction held.
Phase 0 shipped the framework plus a few resolvers; the rest are added incrementally (the
implementation plan sequences this), and the palette reflects whatever is registered.

**Rarity / "random chance of firing"** is separate from requirements and already handled:
it is the **draw weight**. The front-door draw picks weighted from the eligible pool, so a
low-weight mission is genuinely rare even when every requirement passes. The tool exposes
it as a "rarity" control. (A hard independent fire-% is *not* added — weight already gives
probabilistic rarity.)

---

## 8. The graph editor: canvas, node page, option page

### 8.1 The canvas

The whole mission visible at once, navigable, wireable.

**Nodes** are boxes. The **entry node** is marked as the start. **Endings** — routes with
no target — terminate at distinct ending markers showing their resolution
rewards/penalties, so every way the mission can end is visible at a glance.

**Edges** are *option → route → target*. A node's options surface as labelled outgoing
connection points. A **Choice/Advance** option (no roll) has one edge. A **Check** option
*fans*: one edge per outcome tier, tier-labelled. A **random-set** route shows as a fan
into a *weighted set* of targets (node A 60% / node B 40%).

**Layout:** auto-layout (dagre/elk-style) by default to keep a 100-node mission readable,
with manual nudging; node positions persist as pure authoring metadata (a `MissionNode`
field pair or sibling layout model, zero engine meaning).

**Live validation overlay:** the canvas continuously highlights graph problems against
the engine's well-formedness rules — a Check option with an empty outcome bucket, an
option with no routes, an unreachable node, a missing/duplicate entry node. Broken
structure is visible *as you build*, not discovered in play.

### 8.2 Drill-down: node page, option page

Navigation is a **drill-down** — canvas (mission) → node page → option page — with a
breadcrumb and a clean surface-back-up. Each level earns its own focused surface.

**The node page:**

- **Node settings:** conflict mode (COINFLIP / VOTE / JOINT) and, for JOINT, the combine
  rule + count; rider config (allowed riders / deny-all); **attached challenges** (§8.4).
- **Node flavor text** — the thin abstract description of the moment.
- **The option list** — a scroll of authored options, each a card you delve into.
  Alongside it, a read-only preview of the **challenge-contributed options** the attached
  challenges will surface at runtime (per the playing character's capabilities).

A node's options come from exactly two sources: **authored options** (hand-placed here,
optionally predicate-gated) and **challenge-contributed options** (from attached
challenges — §8.4). There is no third "affordance" mechanism; see §8.4 and §11.

**The option page** (authored options only — challenge-contributed options are configured
on the challenge, in its sibling tool):

- **Kind:** **Choice/Advance** (routes the graph, no dice — the engine's `BRANCH`) or
  **Check** (an inline `CheckType`).
- **Option text** — what the player sees as the choice.
- The **predicate gate** — the §7 requirements builder, deciding whether this option
  shows for a given character.
- **Routes** — the structured heart (§8.3).

### 8.3 Routes & outcome tiers

A **Check** resolves not to pass/fail but to a graded **outcome tier** on the
`world.traits.CheckOutcome` ladder (a fumble at the bottom, through near-miss failure and
marginal success, up to a critical — six tiers currently; data-driven). A
`MissionOptionRoute` is keyed to one tier and says: "if the check lands in this tier —
advance *here*, apply *this* consequence, emit *these* rewards, show the player *this*
outcome text."

**Binary by default, split on demand.** A new Check option opens with exactly two routes:
*Success* and *Failure*. Authoring those two covers everything — the whole success bucket
(marginal/solid/critical) routes one way, the whole failure bucket (near-miss/fumble) the
other. Two clicks, done. When a mission earns finer granularity, you **split a bucket** —
peel a tier into its own route ("Critical gets its own glorious outcome").

The engine's route-set-completeness rule (full per-tier coverage) is reconciled at
**publish**: the two buckets expand to complete per-tier coverage automatically. The
validation overlay nags only if a bucket is genuinely *empty*.

*Implementation fork:* draft stores buckets and publish expands, vs. the tool gangs
per-tier rows behind the UI. Either way the ergonomics are two clicks, not six.

**Random outcomes — first-class.** A route's outcome need not be one fixed thing. A route
can be a **weighted random pool**: success → the engine rolls one of {A 50%, B 30%,
C 20%}. The engine already randomises the *destination* (`is_random_set` + weighted
`MissionOptionRouteCandidate`). A true random *outcome* is destination + consequence +
rewards + outcome-text, so `MissionOptionRouteCandidate` is **enriched** to optionally
carry its own consequence, rewards, and outcome text (§11). Then any route — Check
tier-route or Choice route — has a "make this a random pool" toggle, and each weighted
entry is a full self-contained outcome bundle, no extra nodes required.

### 8.4 Attached challenges

A node can **attach one or more `ChallengeTemplate`s**. Each attached challenge
**contributes options** to the node — and this is the *only* automatic option mechanism.
It replaces what missions Phase 1 built as the `Affordance` / `AffordanceBinding` system;
that system is retired (see §11, and `docs/plans/2026-05-22-challenge-missions-integration-findings.md`
for the full reasoning — it was an accidental reinvention of capability-driven option
surfacing, built while missions were decoupled from `mechanics.ChallengeTemplate`).

A `ChallengeTemplate` is a reusable, named obstacle — authored in its own sibling tool
(§2); Mission Studio only *references* it. It is a set of **capability-keyed approaches**
plus a **universal default approach**. The pit-climb example:

- (can fly) → "Fly out" → auto-success
- (has magical climbing) → "Magically run up the wall" → trivial check
- (default, anyone) → "Climb bare-handed" → hard Dexterity + Athletics check

**Attaching a challenge to a node populates the node with challenge-contributed options.**
At runtime, each approach the playing character qualifies for surfaces as an option (the
default always included). The player picks the approach they want; the tool lists
capability, it does not editorialise about what is "smart."

**The division of ownership** — settled as the *data-source* integration shape (findings
doc Q2):

- The **challenge** contributes each option's *existence*, its *capability gate*, and its
  *check* (the approach's `CheckType`, or auto-success).
- The **mission** owns everything downstream of the outcome: the routes, consequences,
  rewards, and outcome text, authored per §8.3 exactly like an authored option's. The
  mission author wires routes for *every* approach the challenge defines; the runtime
  surfaces the per-character subset.
- Mission resolution stays entirely within `resolve_option`. `resolve_challenge`,
  `ChallengeInstance`, and `CharacterChallengeRecord` are **not** invoked by missions — a
  challenge is consumed as authored *data*, not run as an *engine*. A character on a
  mission stays `engagement_type = MISSION`.

No "challenge→outcome bridge" is needed: a challenge approach already runs `perform_check`
and yields a normal `CheckOutcome`, the same currency missions route on.

**Still open (findings doc Q3, Q4), to settle before the implementation plan:** how an
approach's *auto-success* ("fly out") is represented; and which `ChallengeTemplate` fields
(`severity` → check difficulty looks right; `challenge_type`, `discovery_type`,
`properties` — likely ignored in a missions context) are meaningful here.

---

## 9. The testing loop

No in-tool simulator — you test by playing in-game. The key enabler:

**Draft missions are testable.** The staff **assign-mission** power instantiates a *draft*
directly onto any character (yours or a test PC), bypassing the giver. You playtest before
you ever publish. Givers only ever surface *published* missions — draft and live stay
cleanly separated.

**Two test paths:**

- *Fast iteration* — direct-assign the draft to a staff persona, play, observe, fix,
  repeat. Skips the giver gate.
- *Full-fidelity* — publish into the staging environment, pick the mission up through its
  giver like any player, exercising the odds/requirements/giver-object path.

**Staff powers:** assign a mission (draft or live) to a character; remove a mission
instance from a character; edit a mission (the Studio editor itself).

**Observation** is the §5 detail panel: during and after a run, the instance's current
node, its deeds, the outcome reached.

**"Player hit a wall" escape hatch:** remove-mission abandons a genuinely stuck instance
immediately; the validation overlay plus editing the mission fixes the root cause for
every future instance.

The adjacent staff tool for freely editing a test persona's sheet values is a
sibling-suite tool — assumed to exist, out of scope here.

---

## 10. Reuse & copy

**What you can copy**, at three granularities: a **single node**; a **sub-branch** (a node
and everything reachable downstream); a **whole mission** (produces a new draft mission).
Copying into an existing mission puts that mission into the editing state (§4). **Nothing
copied is ever auto-live.**

**Copy carries everything — mechanics and flavor text.** The mechanical skeleton (option
kinds, inline check types, route topology, bucket splits, random-pool structure and
weights, reward scaffolding, predicate gates, conflict mode, riders, attached-challenge
references) comes across intact. So do the three flavor fields — node text, option text,
per-outcome text — but **flagged** with a visible "inherited copy — rewrite me" marker.
The old wording is present as reference and starting point; editing the field clears the
flag.

The anti-same-y discipline is **non-destructive**: a nudge, not a blank. It gets teeth at
publish — the tool can report "N flavor fields are still flagged as un-rewritten copy" so
accidental copy-paste never ships, without ever forcing a retype from a second window.

**Dangling routes:** copying a sub-branch re-points routes *within* the copied set to the
copies automatically; routes that pointed *outside* it come in unwired and flagged in the
validation overlay.

**No fragment palette.** A missions-only "named node-sequence" library would be a second
reuse mechanism for something the codebase already has a home for: reusable gameplay
patterns *are* `Challenge`s (§8.4), referenced by nodes. MVP reuse is plain
copy-from-any-mission; the mission library is its own fragment source.

---

## 11. Engine model extensions required

The authoring vision needs the merged missions engine to grow. Consolidated:

1. **`MissionCategory`** — a lookup model; `MissionTemplate` gains a multi-select M2M to
   it. Categories are content-type tags (assassination, investigation, courtly, heist…),
   multi-valued per mission. A `MissionCategory` is a proper model (not free text) so it
   can later carry a relationship to path aspects when a category→aspect-bonus mechanic is
   built — that mechanic is a future resolution-engine feature, not authoring.
2. **Giver model extension:** a `giver_kind` discriminator (NPC / environmental-detail /
   room-trigger) via `DiscriminatorMixin`; the giver↔mission `templates` M2M becomes a
   through-model carrying optional per-link odds/requirements overrides.
3. **`MissionGiverStanding`** — generalise `MissionGiverCooldown` into a per-(giver,
   character) model holding cooldown *and* a standing/affection value. New predicate leaf
   `giver_standing_at_least`.
4. **Node editor-layout metadata** — persisted canvas positions for `MissionNode`. Pure
   authoring metadata, no engine meaning.
5. **Draft/publish working-draft mechanism** — see §4 (implementation fork open).
6. **Tier bucketing** — binary success/failure default with split-on-demand; per-tier
   completeness reconciled at publish (implementation fork open, §8.3).
7. **`MissionOptionRouteCandidate` enrichment** — optionally carry its own consequence,
   rewards, and outcome text, so a single route can fan into fully-distinct random
   outcomes without a node per flavour.
8. **Flavor-field "needs rewrite" flag** — on the three flavor fields. Authoring metadata.
9. **Retire `Affordance` / `AffordanceBinding`** — remove the missions Phase 1 affordance
   system (`Affordance`, `AffordanceBinding`, `bindings_for_character`, the resolver
   dispatch, their tests, a migration). It was an accidental reinvention of
   capability-driven option surfacing; its job is now split between authored
   predicate-gated options and challenge-contributed options. A node's `accepted_affordances`
   becomes `attached_challenges` (a reference to `mechanics.ChallengeTemplate`). See the
   findings doc for the full reasoning.
10. **Challenge attachment** — a `MissionNode` references `ChallengeTemplate`(s); the engine
    expands each attached challenge's approaches into challenge-contributed options at
    runtime, resolved through `resolve_option` (data-source shape — §8.4). Two sub-items
    remain open (Q3 auto-success representation, Q4 which `ChallengeTemplate` fields apply
    in a missions context) — settle before the implementation plan.
11. **Predicate leaf-resolver registry expansion** — resolvers for level, org membership,
    society/org reputation, achievement, codex entry, resonance type, giver standing, etc.
    Incremental; the requirements-builder palette reflects whatever is registered.

---

## 12. Open questions & deferred work

- **Challenge integration Q3 & Q4** — the two remaining reconciliation questions from the
  findings doc: (Q3) how an approach's auto-success is represented; (Q4) which
  `ChallengeTemplate` fields apply in a missions context. Settle before the implementation
  plan. Q1 (the affordance/challenge duplication) and Q2/Q5 (data-source shape; missions
  reference challenges) are **resolved** — see §8.4 and §11.9–10.
- **"Social capability" derivation** — modelling achievement / reputation / NPC-affection
  as derived capabilities (so a social challenge can have approaches keyed on them) is a
  wanted *capability-system* enhancement, separate from missions authoring. Today
  capabilities derive only from traits (`TraitCapabilityDerivation`); an
  achievement/reputation→capability path would be new. When it exists, challenges and the
  predicate builder both benefit automatically; missions authoring needs no special
  knowledge of it.
- **Node→room binding** — required for go-live, sequenced as the in-progress-persistence
  follow-up. Nodes are abstract in MVP authoring.
- **Giver-standing movement mechanic** — flirt/seduce checks against an NPC giver. Adjacent
  gameplay work; the authoring tool only needs to *express* standing as a requirement.
- **Reward payload enrichment** — resonance-type and legend-range search facets depend on
  it (the deferred reward-payload work from the missions back-door phase).
- **Sibling staff creation tools** — challenge / room / item / NPC creators. Out of scope;
  Mission Studio is built to reference and hand off to them (§2).
- **Category → path-aspect bonuses** — a future resolution-engine feature; the
  `MissionCategory` model is built so as not to block it.
- **Missions vs. Situations long-term** — `mechanics.SituationTemplate` is itself a
  scenario system. Missions and Situations coexist (both GM/staff scenario tooling, both
  consuming `Challenge`s); whether that stays permanent is a broader architectural
  question, out of scope here but recorded.

## Explicitly rejected

- **The missions `Affordance` / `AffordanceBinding` system** — retired as an accidental
  reinvention of capability-driven option surfacing (§11.9). Node options come from
  authored predicate-gated options and challenge-contributed options only.
- **A fragment palette** — reusable gameplay patterns are `Challenge`s, not missions-only
  node-sequence fragments (§10).
- **A hard independent fire-% gate** — draw weight already gives probabilistic rarity (§7).
- **An in-tool mission simulator** — testing is in-game play with a staff persona (§9).
- **Draft/publish as a safeguard** — it is a workflow state; the tool has a single trusted
  author (§2).

---

## Next step

Settle the two remaining challenge-integration questions (findings doc Q3 & Q4), then turn
this into an implementation plan (`superpowers:writing-plans`). The plan must sequence: the
`Affordance`/`AffordanceBinding` retirement and the engine model extensions (§11) ahead of
the tool that depends on them; the predicate leaf-resolver build-out; and the challenge
attachment (§8.4) — now a concrete data-source integration, no longer an open architectural
question.
