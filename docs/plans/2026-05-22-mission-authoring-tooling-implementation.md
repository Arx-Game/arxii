# Mission Authoring Tooling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build "Mission Studio" — a staff React tool for authoring the missions content the merged missions engine can otherwise only be fed by hand-written ORM calls.

**Architecture:** Five phases, each a standalone PR. Phases A–D are backend (engine model changes, predicate resolvers, DRF API) and are fully task-detailed with TDD steps. Phase E is the React tool, specified at the component/API-contract level — the exact TSX of a visual graph editor emerges during the build; the plan fixes the surfaces, contracts, libraries, and test expectations.

**Tech Stack:** Django + Evennia, `SharedMemoryModel`, DRF + drf-spectacular, FactoryBoy, Postgres (+ the SQLite inner-loop test tier), `ty`, ruff; React + TypeScript + Vite, `@xyflow/react` (React Flow) for the graph canvas, the existing staff-frontend shell.

**Source design:** `docs/plans/2026-05-22-mission-authoring-tooling-design.md` (§ refs throughout) and `docs/plans/2026-05-22-challenge-missions-integration-findings.md`.

---

## Phasing & PR strategy

| Phase | PR | Depends on | Summary |
|---|---|---|---|
| A | "Replace affordances with challenge attachment" | — | Retire the missions `Affordance`/`AffordanceBinding` system; add `MissionNode.attached_challenges` + `ChallengeApproach.auto_succeeds`; re-source node options. Engine only. |
| B | "Missions authoring model extensions" | A | `MissionCategory`, giver extension + standing, route-candidate enrichment, node layout metadata, flavor-flag, draft/publish working-draft. Engine only. |
| C | "Predicate leaf-resolver expansion" | B | New predicate leaves the requirements builder needs. Engine only. |
| D | "Mission Studio backend API" | B, C | DRF viewsets/serializers for browse/search/detail, editor CRUD, giver library, draft/publish, copy, staff powers. |
| E | "Mission Studio frontend" | D | The React tool: browser, graph canvas, node/option pages, predicate builder, giver editor, staff-power UI. |

Each phase: branch from `main`, implement, full PG-parity test gate, PR. Do not start a phase until its dependency PR is merged. Within a phase, commit per task.

**General rules for every task:** TDD (failing test first). `arx test --sqlite world.<app>` for the inner loop where the app is SQLite-clean; `echo "yes" | uv run arx test --postgres ...` before pushing. `ruff check` + `ty check` on touched files. Absolute imports. `SharedMemoryModel` for concrete models. New migrations via `arx manage makemigrations <app>`. No `&&` compound bash; use `git -C`.

---

## Phase A — Replace affordances with challenge attachment

**PR goal:** missions option-sourcing moves from the (duplicative) affordance system to challenge attachment. After this PR a `MissionNode`'s non-authored options come from attached `ChallengeTemplate`s. See design §8.4, §11.9–10; findings doc §4 Q1–Q4.

**Why retire and add in one PR:** retiring affordances alone would leave the engine with no automatic option source until challenge attachment lands. Doing both together is one coherent swap and keeps every intermediate commit's tests honest.

### Task A1: `ChallengeApproach.auto_succeeds`

**Files:**
- Modify: `src/world/mechanics/models.py` (the `ChallengeApproach` class)
- Migration: `src/world/mechanics/migrations/000N_challengeapproach_auto_succeeds.py` (generated)
- Test: `src/world/mechanics/tests/test_property_models.py` or a new `test_challenge_models.py`

**Steps:**
1. Write a failing test: a `ChallengeApproach` created with `auto_succeeds=True` round-trips; default is `False`.
2. Run it — fails (no field).
3. Add `auto_succeeds = models.BooleanField(default=False, help_text="When true, this approach skips the roll and lands in the top outcome tier — the capability trivializes the obstacle.")` to `ChallengeApproach`.
4. `arx manage makemigrations mechanics` — one migration, mechanics-only.
5. Run the test — passes.
6. `ruff check` + `ty check` the touched files.
7. Commit: `feat(mechanics): add ChallengeApproach.auto_succeeds`.

### Task A2: `MissionNode.attached_challenges`

**Files:**
- Modify: `src/world/missions/models.py` (`MissionNode`)
- Migration: `src/world/missions/migrations/000N_missionnode_attached_challenges.py`
- Test: `src/world/missions/tests/test_models_node.py`

**Steps:**
1. Failing test: a `MissionNode` can attach a `ChallengeTemplate`; `node.attached_challenges.all()` returns it; default empty.
2. Run — fails.
3. Add `attached_challenges = models.ManyToManyField("mechanics.ChallengeTemplate", related_name="+", blank=True, help_text="Challenges whose approaches surface as options on this node.")`. Add a `cached_property` `cached_attached_challenges` returning `list(self.attached_challenges.all())` for `Prefetch(to_attr=)` use.
4. `makemigrations missions`.
5. Run test — passes.
6. Commit: `feat(missions): add MissionNode.attached_challenges`.

### Task A3: challenge-option expansion service

**Files:**
- Create: `src/world/missions/services/challenge_options.py`
- Test: `src/world/missions/tests/test_services_challenge_options.py`

**What it does:** given a `MissionNode` and a character, return the challenge-contributed options — one `ResolvedOption`-equivalent per `ChallengeApproach` of each attached challenge that the character qualifies for (the character holds the approach's `Application.capability`), the universal default approach always included. Each carries: the approach, its `check_type`, whether it `auto_succeeds`, the challenge's `severity` as difficulty.

**Steps:**
1. Failing test: a node with one attached challenge that has 3 approaches (one auto-success, one keyed on capability X, one default) → a character with capability X gets {auto-success, X, default}; a character without X gets {auto-success, default}. (Use `mechanics.factories` `ChallengeTemplateFactory`/`ChallengeApproachFactory`/`ApplicationFactory`.)
2. Run — fails (no module).
3. Implement `challenge_options_for_character(node, character) -> list[ChallengeOption]`. Reuse the Phase-0 `_resolve_has_capability` predicate resolver for the capability check (single definition of "owns capability"). Define a frozen `ChallengeOption` dataclass in `world/missions/types.py`. Walk `node.cached_attached_challenges`; for each, `select_related` the approaches' `application__capability` + `check_type`; filter by capability ownership (default approach — the one whose `Application` everyone satisfies, or a designated default — always in).
4. Run test — passes.
5. Commit: `feat(missions): challenge-option expansion service`.

> **Design note for the executor:** "the universal default approach" — confirm with the challenge model how the default is identified (an `Application` keyed on a capability every character has, or a convention). If there is no clean "default" marker, raise it before implementing — do not guess.

### Task A4: route challenge-options through `resolve_option`

**Files:**
- Modify: `src/world/missions/services/resolution.py` (`present_options_for_character`, `resolve_option`)
- Test: `src/world/missions/tests/test_services_resolution_resolve.py`, `test_services_resolution_options.py`

**Steps:**
1. Failing test: `present_options_for_character` on a node with attached challenges returns the challenge-options alongside authored options; resolving a challenge-option runs the approach's check (or auto-succeeds → top tier) and routes on the resulting `CheckOutcome`. An `auto_succeeds` option produces the top-tier outcome without a roll.
2. Run — fails.
3. Implement: `present_options_for_character` unions authored options + `challenge_options_for_character`. `resolve_option`, for a challenge-option, runs `perform_check(character, approach.check_type, target_difficulty=challenge.severity)` — or, if `auto_succeeds`, synthesizes a top-tier `CheckOutcome` result with no roll. Routing is unchanged: it keys on the `CheckOutcome`. The mission author's authored routes (Task B / existing) handle the rest.
4. Run tests — pass.
5. Commit: `feat(missions): resolve challenge-contributed options`.

### Task A5: retire `Affordance` / `AffordanceBinding`

**Files:**
- Delete: `src/world/missions/services/affordances.py`; the `Affordance`/`AffordanceBinding` classes from `models.py`; `MissionNode.accepted_affordances`; affordance factories; affordance tests; `OptionProduces`/`SourceKind` constants if now unused.
- Modify: anything importing the above (`resolution.py`, `mission_graph.py`, serializers, `__init__.py` exports).
- Migration: `src/world/missions/migrations/000N_retire_affordances.py` — drops `Affordance`, `AffordanceBinding`, `MissionNode.accepted_affordances`.
- Test: remove affordance tests; ensure the suite is green.

**Steps:**
1. Grep `git -C ... grep -rln "Affordance\|affordance\|accepted_affordances\|bindings_for_character" src/world/missions` — inventory every reference.
2. Remove the models, service, constants, factories, tests, exports. Update `resolution.py` (the affordance-sourcing path is already replaced by A4).
3. `makemigrations missions` — produces the drop migration.
4. `echo "yes" | uv run arx test --postgres world.missions` — green.
5. `ruff check` + `ty check` `src/world/missions`.
6. Commit: `refactor(missions): retire Affordance/AffordanceBinding (replaced by challenge attachment)`.

### Task A6: Phase-A regression gate

Run `echo "yes" | uv run arx test --postgres world.missions world.mechanics` fresh-DB. Green → push branch, open the Phase A PR.

---

## Phase B — Missions authoring model extensions

**PR goal:** the model changes the authoring tool needs (design §11.1–8). Engine only — no tool yet. Branch from `main` after Phase A merges.

### Task B1: `MissionCategory`

**Files:** `src/world/missions/models.py`, `constants.py` if needed, migration, `factories.py`, `test_models_category.py`.

**Steps:**
1. Failing test: a `MissionCategory` round-trips by `name`; `MissionTemplate` can attach several (`template.categories.all()`); default empty.
2. Implement `MissionCategory(NaturalKeyMixin, SharedMemoryModel)` — `name` unique CharField, `description` TextField blank. `MissionTemplate` gains `categories = ManyToManyField(MissionCategory, related_name="templates", blank=True)`.
3. `makemigrations missions`. Factory. Run tests.
4. Commit: `feat(missions): MissionCategory + MissionTemplate.categories`.

### Task B2: giver model extension

**Files:** `src/world/missions/models.py` (`MissionGiver`, new through-model), `constants.py` (`GiverKind` TextChoices), migration, factories, `test_models_giver.py`.

**Steps:**
1. Failing tests: a `MissionGiver` has a `giver_kind` (NPC / ENVIRONMENTAL_DETAIL / ROOM_TRIGGER) selecting which target FK is meaningful, validated by `DiscriminatorMixin`; the giver↔mission link is a through-model carrying optional per-link `weight`/requirements overrides.
2. Add `GiverKind` to `constants.py`. Extend `MissionGiver` with the discriminator + the typed target FKs (NPC `ObjectDB`, environmental-detail `ObjectDB`, room-trigger — confirm what a room-entry trigger references; likely `flows.Trigger` or a room FK — raise if unclear). Convert the `templates` M2M to an explicit through-model `MissionGiverOffering(giver, template, weight_override, ...)`.
3. `makemigrations missions`. Factories. Run tests (RED-first per the `DiscriminatorMixin` `save()`→`clean()` pattern).
4. Commit: `feat(missions): giver kind discriminator + giver-offering through-model`.

### Task B3: `MissionGiverStanding`

**Files:** `src/world/missions/models.py`, migration, factory, `test_models_giver_standing.py`.

**Steps:**
1. Failing test: a per-(giver, character) `MissionGiverStanding` holds `available_at` (cooldown) **and** an `affection`/standing integer; `UniqueConstraint(giver, character)`.
2. Generalise the existing `MissionGiverCooldown` into `MissionGiverStanding` (rename + add `affection = IntegerField(default=0)`), OR add `affection` to `MissionGiverCooldown` and rename. Update `accept_mission`/`offer_missions` callers. Migration.
3. Run the giver/availability test suites — green.
4. Commit: `feat(missions): MissionGiverStanding (cooldown + affection)`.

### Task B4: `MissionOptionRouteCandidate` enrichment

**Files:** `src/world/missions/models.py` (`MissionOptionRouteCandidate`), migration, `test_models_route.py`.

**Steps:**
1. Failing test: a `MissionOptionRouteCandidate` can optionally carry its own `consequence` FK, reward lines, and outcome text — so a random pool entry is a full self-contained outcome bundle (design §8.3).
2. Add the nullable fields. Migration.
3. Run tests. Commit: `feat(missions): enrich MissionOptionRouteCandidate with per-candidate outcome bundle`.

### Task B5: node editor-layout metadata

**Files:** `src/world/missions/models.py` (`MissionNode`), migration, `test_models_node.py`.

**Steps:**
1. Failing test: a `MissionNode` persists `editor_x` / `editor_y` (canvas position); default 0.
2. Add the two `IntegerField`s (or a single small `MissionNodeLayout` sibling model if preferred — `MissionNode` is `SharedMemoryModel`, two ints on it is fine). Pure authoring metadata, no engine meaning. Migration.
3. Commit: `feat(missions): node editor-layout metadata`.

### Task B6: flavor-field "needs rewrite" flag

**Files:** `src/world/missions/models.py` (the three flavor-text-bearing models — node, option, route), migration, tests.

**Steps:**
1. Failing test: node text / option text / per-route outcome text each have a companion `<field>_needs_rewrite` boolean; default `False`.
2. Add the flags. Migration. (The copy operation in Phase D sets them `True`; editing clears them.)
3. Commit: `feat(missions): flavor-field needs-rewrite flags`.

### Task B7: draft/publish working-draft mechanism

**Files:** `src/world/missions/models.py`, `src/world/missions/services/publishing.py` (new), migration, `test_services_publishing.py`.

**This is the most complex task in Phase B.** Design §4: a mission has a draft graph (always what the editor edits) and, once published, a live version; editing is a session; publish atomically updates the live version; in-flight instances are pinned to their version.

**Steps:**
1. Failing tests for the behavioural contract: (a) a new mission is draft-only and `offer_missions` never returns it; (b) editing a published mission's draft does not change what `offer_missions`/new instances see until `publish`; (c) `publish` atomically swaps; (d) an in-flight `MissionInstance` is unaffected by a re-publish.
2. Choose the mechanism (design §4 flagged this fork): recommended — a `MissionTemplate.status` (DRAFT/PUBLISHED) plus, for editing a published mission, a working-copy draft `MissionTemplate` linked to the live one; `publish` promotes. `MissionInstance` gains a FK to the exact template version it was created from (it likely already FKs the template — confirm it pins correctly). Implement `publish(template)` and `open_for_edit(template)` services.
3. Run the contract tests — green.
4. Commit: `feat(missions): draft/publish working-draft mechanism`.

> **Executor note:** this task may itself want splitting into 3–4 commits (status field; working-copy fork; publish service; instance version-pinning). Break it down when you reach it.

### Task B8: Phase-B regression gate

`echo "yes" | uv run arx test --postgres world.missions`. Green → push, open the Phase B PR.

---

## Phase C — Predicate leaf-resolver expansion

**PR goal:** the predicate leaves the requirements builder (design §7) needs. Each is a small registry addition mirroring the Phase-0 resolver pattern. Branch from `main` after Phase B merges.

### Tasks C1–CN: one resolver per leaf type

For each of: character level, org membership, society reputation tier, org reputation tier, achievement held, codex entry unlocked, resonance type held, giver standing — one task:

**Files (per resolver):** `src/world/missions/predicates.py` (register the leaf + resolver), `src/world/missions/tests/test_resolvers.py`.

**Steps (per resolver):**
1. Failing test: the leaf evaluates `True`/`False` correctly against a character with / without the thing. Use the relevant app's factories.
2. Implement the resolver function; register it in the leaf-resolver registry. Reuse the canonical service of the owning app (e.g. `world.conditions.services.has_condition`, the societies reputation accessor) — never re-query; see the Phase-0 precedent and the `feedback_trust_identity_map` discipline.
3. Run test — passes. Commit: `feat(missions): <leaf> predicate resolver`.

**Caveats for the executor:**
- The **giver-standing** resolver depends on `MissionGiverStanding` (Phase B3).
- **Society/org reputation** — Phase 0 stub-sealed `min_society_standing` because reputation is persona-keyed and ambiguous. Resolve that ambiguity (which persona?) before implementing; raise it if unclear.
- **Resonance type held** — depends on the resonance system being queryable; if the typed-resonance data isn't there yet, stub-seal this one leaf with a `# DESIGN` note rather than guessing.

### Task C-final: Phase-C regression gate

`echo "yes" | uv run arx test --postgres world.missions`. Green → push, open the Phase C PR.

---

## Phase D — Mission Studio backend API

**PR goal:** the DRF API the React tool consumes. Branch from `main` after Phases B + C merge. Follow the project's ViewSet conventions (filters, pagination, permission classes; `@extend_schema` for non-`ModelViewSet` viewsets per `project_drf_spectacular_viewset_break`). Staff-only — a single `IsStaff` permission class on everything.

### Task D1: mission browse/search/detail API

**Files:** `src/world/missions/views.py`, `serializers.py`, `filters.py`, `urls.py`; `tests/test_api_browse.py`.

- A `MissionTemplateViewSet` (staff-only) — list with a `FilterSet` covering name, level band, area (giver→room→`Area`), category, risk, org, status; ordered queryset for stable pagination.
- A detail action returning the §5 footprint: lifetime completions (+ who/outcome), active instances (+ current node) — read over `MissionInstance`/`MissionParticipant`/`MissionDeedRecord`.
- TDD per endpoint: failing API test (status + shape) → serializer/view → pass → commit.

### Task D2: editor CRUD API

**Files:** as D1 + nested viewsets.

- CRUD for `MissionNode`, `MissionOption`, `MissionOptionRoute`, `MissionOptionRouteReward`, `MissionOptionRouteCandidate`, node `attached_challenges`, node `editor_x/y`. Per the project's "separate ViewSet for related-model CRUD" rule — nodes/options/routes get their own viewsets, not custom actions on the template viewset.
- Validation belongs in serializers. The graph well-formedness checks (entry-node uniqueness, route-set completeness) surface as serializer validation + a dedicated `validate/` action returning the §8.1 overlay data.
- TDD per endpoint. Commit per viewset.

### Task D3: giver library API

CRUD for `MissionGiver` (+ `giver_kind` discriminated targets), `MissionGiverOffering`, `MissionGiverStanding`. TDD per endpoint.

### Task D4: draft/publish + copy + staff-power actions

- `publish` / `open-for-edit` actions wrapping the Phase B7 services.
- `copy` action(s): copy node / sub-branch / whole mission — re-point internal routes, flag external routes, set every flavor field's `needs_rewrite=True`, land result as draft (design §10).
- Staff-power endpoints: assign a mission (draft or live) to a character; remove a mission instance. These wrap existing missions services where possible.
- TDD per action.

### Task D5: predicate-tree API + schema regen

- Endpoints to read/write a node-or-giver `availability_rule` / option predicate tree, and to list the available leaf types (drives the builder palette — Phase C's registry).
- `just gen-api-types` to regenerate `src/schema.json` + `frontend/src/generated/api.d.ts`. Verify with `pnpm build` (per `feedback_pnpm_typecheck_not_build`).

### Task D6: Phase-D regression gate

`echo "yes" | uv run arx test --postgres world.missions`; `pnpm build`. Green → push, open the Phase D PR.

---

## Phase E — Mission Studio frontend

**PR goal:** the React tool. Branch from `main` after Phase D merges. Component-level tasks — each task fixes files, the API contract consumed, component responsibilities, and Vitest expectations; exact TSX emerges in the build. Lives in the existing staff-frontend shell (design §2 — shared shell, the `pick existing · create new · jump to edit` cross-tool reference pattern).

### Task E1: mission browser + search + detail panel (design §5)

**Files:** `frontend/src/missions/` — a `MissionBrowser` page, a `MissionDetailPanel`, a search/filter bar, query hooks over the D1 API. Vitest: filter interactions, the detail panel's completions/active-instances render.

### Task E2: the graph canvas (design §8.1)

**Files:** a `MissionCanvas` component on `@xyflow/react`. Nodes as boxes; entry node + ending markers; edges = option→route→target with tier labels; random-set fans; auto-layout (dagre) with manual nudge persisting `editor_x/y` via D2. The live validation overlay consumes D2's `validate/` action. Vitest: node render, edge render, the validation overlay surfacing a seeded route-gap.

### Task E3: node page + option page (design §8.2, §8.4)

**Files:** a `NodePage` (node settings, flavor text, authored-option list, attached-challenges with the cross-tool picker, challenge-contributed-option preview) and an `OptionPage` (kind, option text, inline `CheckType`, predicate gate, routes). Drill-down navigation with breadcrumb. Vitest: drill-down navigation, the binary-default/split route UI (§8.3), the random-pool toggle.

### Task E4: the requirements predicate builder (design §7)

**Files:** a `PredicateBuilder` component — AND/OR/NOT group nodes, leaf rows; palette driven by D5's leaf-type list. Reused by the giver editor and the option page. Vitest: build a nested tree, serialize to the `availability_rule` shape, round-trip.

### Task E5: the giver editor (design §6)

**Files:** a `GiverLibrary` + `GiverEditor` — `giver_kind` picker, room + giving-object reference (cross-tool pattern), the giver-offering odds/requirements (reusing E4). Vitest: kind switching, offering edit.

### Task E6: staff-power UI + the flavor-rewrite flagging

**Files:** assign/remove-mission controls (design §9); the "N flavor fields still flagged as un-rewritten copy" surface (design §10); the copy actions wired to D4. Vitest: the flag surface, copy flow.

### Task E7: Phase-E gate

`pnpm typecheck`, `pnpm lint`, `pnpm build`, `pnpm test`. Then a manual smoke: author a small mission end-to-end, publish, assign to a staff persona, play it. Green → push, open the Phase E PR.

---

## Cross-cutting reminders

- **Tests:** backend phases use the SQLite inner-loop tier (`just test-fast world.missions`) for iteration where the app is SQLite-clean, and `echo "yes" | uv run arx test --postgres ...` as the pre-push gate. `world.missions` is SQLite-clean; `world.mechanics` is mostly clean — verify per `docs` and tag PG-required tests `@tag("postgres")`.
- **Migrations:** one per task, app-scoped; never let `makemigrations` produce phantom Evennia migrations — if it does, stop and investigate.
- **New app in CI:** Mission Studio adds no new app (it lives in `world.missions` + `frontend`), so `lint_shard_coverage` is satisfied — but if any new app appears, add it to a CI shard.
- **The `MODEL_MAP.md`** should be regenerated after Phases A–B land significant model changes (`tools/introspect_models.py` → `write_model_map()`).
- **drf-spectacular:** any non-`ModelViewSet` viewset needs `@extend_schema` + the paginated-response helper (`project_drf_spectacular_viewset_break`).

---

## Execution handoff

Recommended: **Subagent-Driven Development**, phase by phase — review at each task boundary, and run the full PG-parity gate at each phase boundary before the PR. Phases A–C are well-suited to tight per-task subagent dispatch; Phases D–E tasks should each be re-broken into finer TDD steps by the implementer when reached.

Sequence is strict: A → B → C → (D needs B+C) → E. Do not parallelize phases — the model dependencies are real.
