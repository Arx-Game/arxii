# Missions — Authoring-Independent Core Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Each task is TDD: write the failing test, run it red, implement minimally, run it green, commit. Use @superpowers:test-driven-development per task.

**Goal:** Build the authoring-independent Missions core — data model, shared predicate evaluator, affordance registry + descriptor bindings, resolution engine, multi-person handling, and front/back-door plumbing — consuming fixture/factory-authored content (the staff editor is a later, separate pass).

**Architecture:** New `world.missions` app. **Reuse the resolution *primitives*, not the Challenge *container*:** `checks.perform_check`, `checks.apply_resolution`, `checks.models.Consequence`/`ConsequenceEffect`, `checks.outcome_utils.{select_weighted,filter_character_loss,build_outcome_display}`, `ResolutionContext`, `world.traits.models.CheckOutcome` are reused directly; the mission graph (template/node/option/instance/deed-record) is built new rather than overloading `ChallengeTemplate`/`ChallengeApproach`/`ChallengeInstance` (those carry combat/situation/reveal semantics — `situation_instance`, `blocked_capability`, `is_revealed` — that do not map to a mission node and would contort both systems). The predicate evaluator is built new (mirrors `DistinctionPrerequisite.rule_json`'s AND/OR/NOT shape; no evaluator exists today). Lookup tables follow `NaturalKeyMixin`/`SharedMemoryModel`; the heterogeneous descriptor→affordance binding uses `core.mixins.DiscriminatorMixin`.

> **DECISION TO CONFIRM (non-blocking; default proceeds):** Design §2 says "ChallengeTemplate ≈ an authored challenge." This plan instead reuses the *check/consequence math* and builds the mission graph natively, because the Challenge models carry semantics missions don't want. Behaviour and the validated §1–§12 design are unchanged; only the implementation substrate differs. If you'd rather literally extend `ChallengeTemplate`, say so before Phase 2 — Phases 0–1 are unaffected either way.

**Tech Stack:** Django + Evennia (`SharedMemoryModel`), DRF (API is a *later* pass — workstreams 1–2 are model+services only), `ty` (new app auto-included once in INSTALLED_APPS), ruff, FactoryBoy. Tests via `arx test` ONLY (`echo "yes" | uv run arx test <module>`); migrations via `arx manage makemigrations missions`.

**Out of scope (deferred per design §13/§14 — build STUB-SEAMs only, do not implement):** authoring UI/API; in-progress persistence beyond the instance model's node-pointer/snapshot; mission-chaining lifecycle decision (forced vs opt-in); rumor/news propagation; crime-watch/law state; instanced-room spawn/teardown; money/currency sink (locate later — emit a structured reward line, don't apply). Each is a named `missions/integrations/*_stub.py` raising `NotImplementedError` with a docstring pointing at the design section.

---

## Conventions (every task)

- Branch: `feature/missions-design` (already current; never main; no worktree).
- After model changes: `arx manage makemigrations missions` then `arx manage migrate`. **One migration per phase**, not per task (squash within a phase before commit) — see `django_notes.md` new-app migration guidance.
- Tests: `echo "yes" | uv run arx test world.missions.tests.<module>` (whole module; `-k` is broken in this runner). Fresh-DB regression (`echo "yes" | uv run arx test world.missions`) before the final phase commit.
- Lint after each task: `uv run ruff check src/world/missions/<file>`; `uv run ty check src/world/missions/<file>` (skip `serializers.py`/tests — ty-excluded; no serializers in this plan).
- `SharedMemoryModel` for all concrete models; lookup tables also `NaturalKeyMixin`. Absolute imports. No `Meta.ordering` unless sequential. TextChoices in `constants.py`. Types/dataclasses in `types.py`. No untyped dict returns — dataclasses.
- Command-shape discipline (esp. if dispatched to subagents): Write/Edit tools (no heredoc/`$()`); `git -C`; forward-slash `/c/...`; background long tests, never `tail`-pipe the runner.

---

## Phase 0 — Shared predicate evaluator

`world.missions.predicates`. One evaluator, AND/OR/NOT tree mirroring `DistinctionPrerequisite.rule_json`; leaves test the *acting character's durable state only* (design §4). Three eventual call sites (option visibility, affordance eligibility, mission availability) — all in missions.

### Task 0.1: rule node types

**Files:** Create `src/world/missions/__init__.py`, `src/world/missions/apps.py`, `src/world/missions/predicates.py`, `src/world/missions/types.py`; Modify `src/server/conf/settings.py` (add `"world.missions.apps.MissionsConfig"` to INSTALLED_APPS); Test `src/world/missions/tests/__init__.py`, `src/world/missions/tests/test_predicates.py`.

- **Step 1 (failing test):** in `test_predicates.py`, `test_and_or_not_compose`: build `{"op":"AND","of":[{"leaf":"always_true"},{"op":"NOT","of":[{"leaf":"always_false"}]}]}` and assert `evaluate(rule, ctx) is True`; an `OR` with all-false is `False`.
- **Step 2:** `echo "yes" | uv run arx test world.missions.tests.test_predicates` → FAIL (module missing).
- **Step 3 (implement):** `apps.py` (`MissionsConfig`, `name="world.missions"`); register in settings. In `predicates.py`:
  ```python
  from dataclasses import dataclass
  from typing import Protocol

  class PredicateContext(Protocol):
      """Read-only durable-state accessor for the acting character.
      Phase 0 ships only the structural evaluator + a stub context;
      leaf resolvers are added in 0.3 as the descriptor systems are wired."""
      def has_leaf(self, leaf: str, **params: object) -> bool: ...

  def evaluate(rule: dict, ctx: "PredicateContext") -> bool:
      if "op" in rule:
          op, of = rule["op"], rule["of"]
          if op == "AND": return all(evaluate(r, ctx) for r in of)
          if op == "OR":  return any(evaluate(r, ctx) for r in of)
          if op == "NOT": return not evaluate(of[0], ctx)
          raise ValueError(f"unknown op {op!r}")
      return ctx.has_leaf(rule["leaf"], **rule.get("params", {}))
  ```
- **Step 4:** test → PASS.
- **Step 5:** `git add … && git commit -m "feat(missions): predicate AND/OR/NOT evaluator skeleton"`.

### Task 0.2: empty/malformed rule contract
Failing test: `evaluate({}, ctx)` and `evaluate({"op":"AND","of":[]}, ctx)` → define + assert (empty AND = True/"no gate"; `{}` = True; unknown op raises `ValueError`). Implement guards. Commit.

### Task 0.3: leaf resolver registry (durable-state leaves)
A `LeafResolver` registry mapping leaf-name → callable `(character, **params) -> bool`. Ship resolvers for the durable descriptors confirmed present: `has_distinction` (slug), `has_achievement` (slug — `world.achievements.models`), `min_society_standing` (`world.societies` standing model — verify exact field in Step 1), `has_condition` (`conditions`), `has_thread` / `min_thread_level` (`world.magic.models.threads.Thread`), `min_trait`/`has_skill` (`world.traits`), `has_capability` (`conditions.CapabilityType`). Each its own failing test against factory-built characters (use `evennia_extensions.factories` + the relevant app factories; `setUpTestData`). **Stub-seam any descriptor whose model is unconfirmed** (raise `NotImplementedError` with a `# DESIGN §4` note) rather than guess a field. One commit per resolver group.

> Skill: @superpowers:test-driven-development. Real factory objects, never mock the ORM.

---

## Phase 1 — Affordance registry + descriptor bindings

### Task 1.1: `Affordance` lookup model
**Files:** `src/world/missions/models.py`, `src/world/missions/constants.py`, `tests/test_models_affordance.py`.
- Failing test: `AffordanceFactory(name="distraction")` round-trips; `natural_key()`/`get_by_natural_key` works; `unique` name.
- Implement:
  ```python
  class Affordance(NaturalKeyMixin, SharedMemoryModel):
      name = models.CharField(max_length=64, unique=True)   # e.g. "distraction", "lethal"
      description = models.TextField(blank=True)
      class NaturalKeyConfig: fields = ["name"]
  ```
  `makemigrations missions` (Phase-1 migration starts here).
- Commit.

### Task 1.2: `AffordanceBinding` (descriptor → affordance spec)
The reusable, authored-once binding (design §3). Uses `core.mixins.DiscriminatorMixin` for the heterogeneous descriptor side (see [[feedback_discriminator_mixin]] convention).
- Failing test: a binding for "Seduction skill, as `distraction`, produces a CHECK using check_type=X, base_risk=2, ic_framing='you work an angle to draw their eye'"; and one for "famous-drunk achievement, as `social-shortcut`, produces a BRANCH"; assert `binding.produces` ∈ {BRANCH,CHECK}; CHECK requires `check_type` non-null, BRANCH forbids it (`clean()` validation).
- Implement `OptionProduces` TextChoices (BRANCH, CHECK) in `constants.py`; `AffordanceBinding(SharedMemoryModel, DiscriminatorMixin)` with: discriminator + typed FKs (`source_trait`, `source_distinction`, `source_achievement`, `source_capability`, `source_technique`, `source_condition` — nullable, exactly-one enforced by DiscriminatorMixin), `affordance` FK, `produces`, `check_type` FK(`checks.CheckType`, null), `base_risk` PositiveSmallInteger, `ic_framing` CharField, `rider` FK(`checks.Consequence`, null — the reusable typed rider, §6). `clean()` enforces produces↔check_type and BRANCH↔no-check.
- Commit.

### Task 1.3: descriptor → bindings query service
`services/affordances.py::bindings_for_character(character, accepted: set[Affordance]) -> list[ResolvedOption]` — gathers every binding whose descriptor the character owns AND whose affordance ∈ accepted. `ResolvedOption` dataclass (`types.py`): `binding`, `produces`, `check_type|None`, `base_risk`, `ic_framing`, `rider|None`, `owner` (the participant; Phase 4 sets, default = the acting char). Failing test with a character who has 2 of 3 tagged descriptors → exactly 2 ResolvedOptions. Commit. (Descriptor-ownership checks reuse Phase 0.3 resolvers.)

---

## Phase 2 — Mission graph data model

All `SharedMemoryModel`. Template/Node/Option are authored (fixture/factory now, editor later). Instance/DeedRecord are per-run.

### Task 2.1: `MissionTemplate`
Fields: `name` (unique), `slug`, `summary` (IC, rich — bookend lore), `epilogue` (IC, rich), `level_band_min`/`level_band_max` (PositiveSmallInt — design §8), `risk_tier` (PositiveSmallInt), `base_weight` (PositiveInt, availability draw), `created_in_era` FK(`stories.Era`, null — arc association §8), `arc_scope` (TextChoices: GLOBAL/ORG/GIVER), `percent_replace` (PositiveSmallInt 0–100), `cooldown` (DurationField — per-giver §8), `is_active`. Failing test: factory round-trip + `clean()` rejects `level_band_min > max` and `percent_replace > 100`. Commit.

### Task 2.2: `MissionNode` + `MissionOption`
- `MissionNode`: `template` FK, `key` (slug, unique per template), `is_entry` (bool, exactly-one-per-template enforced in `clean()`/test), `conflict_mode` (TextChoices COINFLIP/VOTE/JOINT — §10), `joint_combine` (TextChoices ANY/ALL/COUNT, null), `joint_count` (PositiveSmallInt, null), `rider_policy` JSON? **No** — use `allowed_riders` M2M(`checks.Consequence`) + `deny_all_riders` bool (constants over JSON; §6 allow/deny).
- `MissionOption`: `node` FK, `order`, `option_kind` (TextChoices BRANCH/CHECK), `source_kind` (TextChoices AFFORDANCE/AUTHORED), `accepted_affordances` M2M(`Affordance`, for AFFORDANCE kind), `visibility_rule` JSONField (the §4 predicate tree — *this* is the one sanctioned dynamic JSON, like `rule_json`; document why), authored-special fields for AUTHORED kind: `authored_check_type` FK(null), `authored_base_risk`, `authored_ic_framing`, plus routing: `branch_target` FK(`MissionNode`, null — BRANCH/authored), and outcome routes via Task 2.3.
- Failing tests: entry-node uniqueness; AFFORDANCE option requires ≥1 accepted_affordance and forbids authored_* ; BRANCH forbids check fields; `visibility_rule` defaults `{}` (= always visible). Commit.

### Task 2.3: `MissionOptionRoute` (outcome-tier → next node)
Per-`MissionOption` rows: `outcome_tier` FK(`traits.CheckOutcome`, null for BRANCH's single route), `target_node` FK(`MissionNode`, null = terminal), `is_random_set` bool (+ `MissionOptionRouteCandidate` child for "pick one of N at random", design §2). Failing test: a CHECK option with success→nodeA, fail→nodeB; a randomized success set of 2 candidates; a BRANCH option with one null-tier route. Commit. **Phase-2 migration: makemigrations+migrate now; squash to one.**

### Task 2.4: `MissionInstance` + `MissionParticipant` + `MissionDeedRecord`
- `MissionInstance`: `template` FK, `current_node` FK(`MissionNode`, null=complete), `status` (TextChoices ACTIVE/COMPLETE/ABANDONED/EXPIRED — persistence detail deferred; just the field), `started_at`, `completed_at` (null). **No scratch vars** (design §7) — state is `current_node` + per-entry snapshot rows.
- `MissionParticipant`: `instance` FK, `character` FK(ObjectDB), `is_contract_holder` bool (exactly-one; the receiver — §10).
- `MissionNodeSnapshot`: `instance` FK, `node` FK, `participant` FK, `taken_at` — the per-node-entry durable-state capture point (design §7; Phase 3 populates; here just the model + "snapshot exists per (instance,node,participant) entry" test).
- `MissionDeedRecord`: `instance` FK, `actor` FK(ObjectDB, the acting participant — moral consequence follows the actor §10), `node` FK, `option` FK, `outcome` FK(`traits.CheckOutcome`, null for BRANCH), `applied_at`, `reward_summary` (structured — see `types.py` `DeedRewardLine` dataclass, NOT a dict). Failing tests for each model's invariants. Commit (squash Phase-2 migration before this commit).

---

## Phase 3 — Resolution engine (reuses check/consequence primitives)

`services/resolution.py`. Pure functions; no API.

### Task 3.1: option-list assembly
`build_option_list(instance, node, viewer: MissionParticipant) -> list[ResolvedOption]`:
- AFFORDANCE options → `bindings_for_character` (1.3) over the option's `accepted_affordances`, unioned across **all participants** (Phase 4 generalizes; Phase 3 = single participant), each tagged with `owner`.
- AUTHORED options → included iff `evaluate(option.visibility_rule, PredicateContext(viewer.character))` (Phase 0).
- Additive merge, stable order (`node` order then binding name). No arbitration (design §3/§6).
- Failing test: a node with 1 AFFORDANCE option (char has 2 matching descriptors → 2 entries) + 1 AUTHORED option gated by a `has_achievement` rule the char lacks → 2 entries, authored hidden; give the achievement → 3 entries. Commit.

### Task 3.2: snapshot-on-entry
`enter_node(instance, node)` writes a `MissionNodeSnapshot` per participant and sets `instance.current_node`. Evaluation cadence = once per entry (design §7). Failing test: entering twice creates two snapshots; option list is computed against the snapshot, not re-queried mid-node. Commit.

### Task 3.3: resolve a CHECK option (reuse `perform_check` + consequence math)
`resolve_option(instance, node, option, actor: MissionParticipant, chosen_binding) -> MissionDeedRecord`:
- CHECK: `check_type` = binding's (AFFORDANCE) or `authored_check_type`; `perform_check(actor.character, check_type, target_difficulty=template.risk/severity mapping)` → `CheckResult`.
- Consequence selection mirrors `mechanics/challenge_resolution.py::_select_consequence` *pattern* (authored-route consequence for the rolled `outcome` tier; synthetic fallback `Consequence(outcome_tier=…, weight=1, character_loss=False)` if none) — reuse `select_weighted` + `filter_character_loss` + `build_outcome_display` from `checks.outcome_utils`.
- Apply via `apply_resolution(PendingResolution(check_result, consequence), ResolutionContext(character=actor.character, …))`.
- **Riders (§6):** if `chosen_binding.rider` and node allows it (`not deny_all_riders` and rider ∈ `allowed_riders`), additively apply the rider as a second `apply_resolution` (composes, not precedence).
- Route to `target_node` for the rolled tier (resolve `is_random_set` via `select_weighted`/uniform over candidates).
- Emit `MissionDeedRecord(actor=actor.character, …)`.
- Failing tests: success routes to A, fail to B; rider applied when allowed and suppressed when denied; synthetic fallback when no authored consequence for the tier; deed-record actor == the acting participant. Commit.

### Task 3.4: resolve a BRANCH option
No check; route to `option.branch_target` (or authored route); emit a deed-record with `outcome=None`. Failing test. Commit.

### Task 3.5: terminal completion → deed-record + structured reward lines
On routing to a null target: set `status=COMPLETE`, emit a terminal `MissionDeedRecord` whose `reward_summary` is a `list[DeedRewardLine]` (each: `kind` ∈ IMMEDIATE/POST_CRON/PROPAGATION, `sink` ∈ MONEY/LEGEND_POINTS/RESONANCE/RUMOR/CRIME_WATCH/BEAT, `payload` typed). **No application here** — emission only (design §9; application is Phase 5). Failing test asserts the structured lines for a sample terminal route. Commit. **Phase-3 has no new migrations.**

---

## Phase 4 — Multi-person

### Task 4.1: participant set + union option list
Generalize 3.1: option list = union over all `instance` participants' eligible options, each `owner`-tagged. Failing test: 2 participants, disjoint descriptor sets → union; AUTHORED visibility evaluated per-the-viewer. Commit.

### Task 4.2: conflict resolution modes
`select_group_choice(node, picks: dict[participant, option]) -> ResolvedChoice`: COINFLIP (uniform among distinct picks), VOTE (plurality, deterministic tiebreak = contract-holder), JOINT (every picker attempts; combine via `joint_combine` ANY/ALL/COUNT≥`joint_count`). Failing tests per mode incl. tie→contract-holder, JOINT ALL one-fail → fail. Commit.

### Task 4.3: actor attribution + contract-holder accounting
Moral consequence + riders → the **actor** who performed the resolving option (design §10): deed-record `actor` = that participant; per-act consequences applied to them only. Terminal reward distributed by `template`-authored group rule (add `MissionTemplate.reward_group_rule` TextChoices ALL_EQUAL/BY_ROLE/BY_PARTICIPATION + a Phase-4 migration). Contractual lines (cooldown, giver-standing, failure-penalty) target **only** `is_contract_holder` (helpers excluded — the funnel is intended). Failing tests: killer gets the moral line, lookout doesn't; terminal reward split per rule; cooldown line names only the contract-holder. Commit (squash Phase-4 migration).

---

## Phase 5 — Front door (availability draw) + back door (reward application + Beat seam)

### Task 5.1: `MissionGiver` (abstract, unpiloted)
`MissionGiver(SharedMemoryModel)`: `name`, `location` FK(ObjectDB, null — grid room of the giver), `org` FK(null — society/org for standing/contract effects; reuse the societies model confirmed in Phase 0.3). M2M `templates` (the pool this giver can offer). Per-giver-per-character cooldown table `MissionGiverCooldown(giver, character, available_at)`. Failing tests. Commit (Phase-5 migration starts).

### Task 5.2: availability draw
`offer_missions(giver, character, risk_dial:int) -> list[MissionTemplate]` (design §8): candidates = giver.templates filtered by (a) `evaluate(template.availability_rule, ctx)` — add `MissionTemplate.availability_rule` JSONField (predicate, reuses Phase 0) in this task's migration; (b) PC level band vs `level_band_*` adjusted by `risk_dial`; (c) not in cooldown. Weighted draw (`select_weighted` over `base_weight`). **Era/arc percent-replace:** if an `Era` is active and a template's `created_in_era`==active era and scope covers this giver, apply per-slot `percent_replace` (each of N slots independently rolls arc-vs-ambient; arc slot drawn from arc-eligible subpool; revert is automatic when the Era concludes — reuse `stories.Era`/`EraManager.get_active()`, no new lifecycle). Failing tests: predicate+band+cooldown filtering; weighting; `percent_replace=100` ⇒ all-arc but still band/predicate-eligible; Era concluded ⇒ ambient returns. Commit.

### Task 5.3: accept → instance; the journal seam
`accept_mission(giver, character) -> MissionInstance` (sets contract-holder, enters entry node via 3.2, starts cooldown). `share_mission(instance, other) -> MissionParticipant` (design §10 — receiver shares; no group entity). Quest-journal is a *read* over `MissionInstance`+`MissionDeedRecord` for that character — add `services/journal.py::journal_for(character)` returning structured `JournalEntry` dataclasses (active node + history). Failing tests. Commit.

### Task 5.4: back-door reward application
`apply_deed_rewards(deed: MissionDeedRecord)`:
- IMMEDIATE/MONEY → **STUB-SEAM** `integrations/money_stub.py` (locate sink later; emit+log, don't apply).
- POST_CRON/LEGEND_POINTS, RESONANCE → enqueue onto a `MissionRewardQueue(deed, kind, payload, applied=False)` row.
- PROPAGATION/RUMOR, CRIME_WATCH → **STUB-SEAM** `integrations/{rumor,crime_watch}_stub.py` raising `NotImplementedError` with `# DESIGN §13.3`.
- Failing tests: queue rows created for legend/resonance; stub-seams invoked (asserted via the stub recording a call), not applied. Commit.

### Task 5.5: cron batch (Legend Points + Resonance)
`services/cron.py::apply_mission_reward_batch()` drains `MissionRewardQueue` (unapplied): LEGEND_POINTS → existing legend-award path (via `checks.ConsequenceEffect` legend fields / `societies.LegendEntry` — verify exact grant entry point in Step 1, STUB-SEAM if not a clean call), RESONANCE → `world.magic` `grant_resonance` service (verify signature in Step 1). Register a `CronDefinition(task_key="missions.reward_batch", …)` in `world.game_clock` `register_all_tasks()` following the `task_registry` pattern. Failing test: queued rows applied + marked `applied=True`, idempotent on re-run. Commit.

### Task 5.6: optional Story Beat seam
**Verify first** whether `stories.Beat.required_mission` exists (substrate map says NO; roadmap says scaffold — Step 1 greps `required_mission` in `src/world/stories/`). If absent, add nullable `Beat.required_mission` FK(`missions.MissionTemplate`) + a stories migration. `on_mission_complete_for_beat(instance)`: iff the instance was launched as a beat resolver (carry `MissionInstance.source_beat` FK, null), emit `BeatCompletion` + fire the existing DAG-advance service (locate `BeatCompletion.objects.create`/`resolve_episode` seam in `stories/services/` in Step 1; call it, do not reimplement). Failing test: free mission ⇒ no BeatCompletion; beat-bound mission ⇒ BeatCompletion created + transition evaluated. Commit (squash Phase-5 migrations).

---

## Final gate (before handoff)

1. `echo "yes" | uv run arx test world.missions` (fresh DB, no `--keepdb`) → OK.
2. `echo "yes" | uv run arx test world.stories world.checks world.mechanics world.game_clock` (touched seams) → OK.
3. `uv run ruff check src/world/missions/`; `uv run ty check src/world/missions/` (excluding tests) → clean.
4. `uv run python tools/introspect_models.py` then `write_model_map()` to refresh `docs/systems/MODEL_MAP.md` (new app); update `docs/systems/INDEX.md` + a `src/world/missions/CLAUDE.md` stub.
5. Adversarial review (@superpowers:requesting-code-review) over the branch — focus: reuse-not-reinvent (no Challenge-model contortion, real `perform_check`/`apply_resolution` usage), predicate evaluator only reads durable state (no target sheet — design §4), no scratch-state, query discipline (`assertNumQueries` on option-list assembly and the availability draw), structured rewards (no dict returns), stub-seams truly inert. Fix Critical/Important; push.

---

## Open / explicitly deferred (do NOT build here)

Authoring UI/API (next design pass); persistence abandon/resume/expiry semantics; chaining lifecycle (forced vs opt-in — design risk vs no-stuck-states); rumor/crime-watch/money real sinks; instanced-room lifecycle; character signature/calling-card. All present only as named inert stub-seams. See `docs/plans/2026-05-18-missions-design.md` §13/§14.

---

## Execution handoff

Plan saved to `docs/plans/2026-05-18-missions-implementation.md`. Two execution options when you're back:

1. **Subagent-Driven (this session)** — fresh subagent per task, two-stage review between tasks, fast iteration (@superpowers:subagent-driven-development).
2. **Parallel Session** — new session runs @superpowers:executing-plans, batch checkpoints.

Recommend Subagent-Driven by phase (review at each phase boundary, not each micro-task — the system is large). Authoring-tooling brainstorm slots in after Phase 2 lands (the schema it edits then exists).
