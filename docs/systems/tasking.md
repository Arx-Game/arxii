# Tasking — the dual-fulfillment job primitive

**App:** `src/world/tasking/` · **Spec:** issue #2820 (phase 1 of 5) · **Since:** 2026-07

An `OrgTask` is a discrete, deadline-bearing job an organization issues against an
authored `TaskTemplate`. Fulfillment is dual: an **NPC agent** (an `assets.NPCAsset`)
resolves it offscreen as a check with tiered outcomes, or — phase 5 — a **PC** runs the
template's linked mission. Both paths grade into the same outcome-route table. This is
the general "an NPC does it as a check, OR a player does it as a mission" primitive the
roadmap keeps needing (spy networks, tax runs, crime jobs, military actions, magical
research); covert-org spycraft (#2820 phases 2–4) is its first consumer.

Deliberately NOT here: standing "stay here until recalled" postings — those are
`npc_services.NPCAssignment` rows (no duration; they persist). Every task ends.

## Models (`models.py`)

- **`TaskTemplate`** — authored job: `name` (natural key), `category`
  (`TaskCategory`: SPYCRAFT/CRIME/DOMAIN/MILITARY/GENERAL), `check_type` FK +
  `check_difficulty` (both the dispatch and resolution rolls), `duration`
  (real time to deadline), `target_kind` (`TaskTargetKind`), `eligibility_rule`
  predicate, nullable `mission_template` FK (set ⇒ PC-fulfillable, phase 5),
  nullable `consequence_pool` FK (ADR-0092 risk surface), `is_active`.
- **`TaskOutcomeRoute`** — per (template, `outcome_tier` FK → `traits.CheckOutcome`)
  payout row: `money_reward`, nullable `clue_pool` FK, `report_template`
  (`{task}`/`{target}`/`{agent}` format kwargs). No route for a tier ⇒ nothing
  happens (fail closed).
- **`OrgTask`** — live instance: `template`, `org`, `issued_by` persona, `status`
  (`TaskStatus`: OPEN→ASSIGNED→RESOLVING→COMPLETED/FAILED/EXPIRED), `deadline`
  (set at assignment), target via `DiscriminatorMixin` (`target_kind` selects
  exactly one of room/org/domain/persona; NONE ⇒ all null).
- **`TaskFulfillment`** — who's on it: `npc_asset` XOR `mission_instance` (clean-
  enforced), `handler` persona, stored dispatch check (`handler_check_outcome`,
  `handler_margin`), `resolved_outcome`, `report`, partial-unique one active row
  per task.

## Services (`services.py`)

- `create_task(template, org, issued_by, *, target_...)` — OPEN instance; caller
  gates leadership.
- `assign_agent(task, npc_asset, handler)` — validates OPEN task, ACTIVE asset,
  handler owns the asset (phase 1; org-owned rows arrive phase 2), handler is an
  active org member. Rolls the handler's **dispatch check**
  (`perform_check_with_modifiers`) immediately; `handler_margin =
  success_level * DISPATCH_MARGIN_STEP` (constants.py, 5). Sets ASSIGNED +
  deadline.
- `resolve_task(task)` — the agent's **resolution check**: `perform_check` on the
  asset persona's character (promotion created a real sheet) with the handler
  margin as extra modifier. Route payouts land on the handler
  (`deliver_mission_money` reason "task reward"; `draw_clue_from_pool` +
  `acquire_clue`). Risk: `select_consequence_from_result` + `apply_resolution`
  over the template's pool with `ResolutionContext(npc_asset=...)` — ASSET_STATUS
  effects hit the dispatched asset only. Writes the report; COMPLETED when
  `success_level > 0`, else FAILED.
- `resolve_due_tasks()` — hourly game-clock cron (`tasking.resolve_due_tasks`,
  registered in `world/game_clock/tasks.py`).
- `target_label(task)` — display label for the discriminated target.

Typed exceptions in `exceptions.py` (`TaskingError` tree, `user_message` per
CodeQL convention).

## Double-check semantics

The handler's dispatch check models briefing quality ("how good is the spymaster
at running agents") — it shifts the agent's odds, never replaces the roll. The
agent's resolution check is the tradecraft; its tier picks the payout route and
grades the risk pool. Asset compromise/loss flows ONLY through consequence pools
(ADR-0092); `ResolutionContext.npc_asset` narrows the effect to the dispatched
agent (see `world/mechanics/effect_handlers.py::_apply_asset_status`).

## API (`views.py`, `/api/tasking/`)

- `templates/`, `routes/` — staff authoring CRUD (`IsAdminUser`).
- `tasks/` — the member board: list/retrieve scoped to the active persona's org
  memberships (non-member ⇒ empty, per IC-reads-scope-to-active-character);
  `POST tasks/` leader-gated (`IsOrgLeaderForCreate` → `is_org_leader`);
  `POST tasks/{id}/assign/` any active member dispatching their own asset.
  Reports serialize only after resolution. Fulfillments reach the serializer via
  a context map on the list path — no `Prefetch` onto SharedMemoryModel parents.

## Frontend

`frontend/src/tasking/` — API client, queries, and `OperationsSection` (read-only
board panel rendered on `OrgPage`, hidden when empty). Issue/assign UI rides
later phases.

## Extension points (later phases of #2820)

- Phase 2: covert-org layer (org-owned `NPCAsset` rows unlock org-roster
  dispatch in `assign_agent`).
- Phase 3: listener loop (`NPCAssignment` LISTENER role — standing posts, not
  tasks).
- Phase 5: PC pickup — `TaskFulfillment.mission_instance` is already in the
  schema; acceptance spawns a `MissionInstance` from `template.mission_template`
  and its outcome tier lands on the same `TaskOutcomeRoute` table.
