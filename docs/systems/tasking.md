# Tasking — the dual-fulfillment job primitive

**App:** `src/world/tasking/` · **Spec:** issue #2820 (all 5 phases) · **Since:** 2026-07

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

## Covert-org layer (phase 2)

- `OrganizationType.is_covert`; `Organization.parent_org` self-FK (structural
  wings — distinct from `FealtyEdge`). Covert orgs excluded from the public
  org-name search (`events.OrganizationSearchViewSet`); org detail/rosters
  were already members-only.
- **Covert joins mint a Secret**: `sync_covert_membership_secret`
  (`societies/membership_services.py`) — subject-anchored, GM-provenance,
  `subject_aware`, back-linked on `OrganizationMembership.covert_secret`.
  Level tracks rank tier (`COVERT_SECRET_LEVEL_BY_TIER`: tier 1 → level 4)
  via promote/demote re-sync; the secret survives leaving. "Who runs the
  network" is playable through the clue→secret machinery.
- **Org-held agents**: `NPCAsset.promoter_org` XOR `promoter_persona`;
  `transfer_asset_to_org` + the `donate` endpoint flip a personal row to the
  org. Succession follows org leadership. `assign_agent` dispatches the
  issuing org's roster.
- **Oversight**: `SPYMASTER_OFFICE` slug on the *parent* org
  (`societies/constants.py`) + parent leadership get READ access to child
  boards (`office_services.can_oversee_org` / `overseen_org_ids`); command
  stays with the child org's rank 1. `/api/tasking/roster/` is the board's
  Roster panel.

## Listener loop (phase 3)

- `AssignmentRole.LISTENER` — a standing `NPCAssignment` (one active per
  room: prime posts are contested; flip the sitting listener, don't stack).
- `ListenerPost` sidecar (`listener_services.py`): buzz meter + threshold +
  optional tradecraft `check_type`. Weekly cron `tasking.listener_sweep`
  accrues `LISTENER_BUZZ_BASE` + per-scene + per-minted-secret from the
  room's **mechanical residue only** — prose is structurally invisible
  (the surveillance-tenet invariant, ADR-0175). Threshold crossings bank a
  `ListenerHarvest` keyed to a real scene-anchored Secret when one exists.
- **Collection is physical**: `collect_harvest` requires the handler's body
  in the room (`POST /api/tasking/posts/{id}/collect/`); a real catch mints
  an AUTOMATIC clue targeting the caught secret (→ SecretKnowledge). The
  visit is the exposure surface.

## Counterplay (phase 4, `counterplay_services.py`)

- **suppress** (Intimidation roll): meter silently freezes for two weeks —
  indistinguishable from bad luck on the board.
- **flip** (Seduction roll): rival gains a CHARM co-owner `NPCAsset` row
  (#2295 pattern) + hidden `flipped_controller` on the post. Real catches
  stop; **plant** queues a red herring (ACCUSATION-provenance secret via
  `mint_accusation` — contestable through `AccusationRebuttal`) that the
  next harvest delivers; the original handler collects it as if real.
- **detect** (Perception roll, consentless): reveals listener agents in the
  room (names only — who they report to is its own investigation).
- **clear** (room owner/tenant standing, consentless): retires the room's
  listener assignments.
- **Consent boundary**: offensive verbs against PC-run networks route
  through the `espionage` consent category (seeded under All Antagonism —
  opt-in by default); the gated owners are the holding persona or the
  holding org's leadership. NPC networks have no PC owners → always-on.
- API: `/api/tasking/counterplay/{suppress,flip,plant,detect,clear}/`.
- Hidden state (`suppressed_until`, `flipped_controller`, `pending_plant`,
  `ListenerHarvest.planted_clue`) is NEVER serialized.

## PC pickup (phase 5)

`accept_task` (board `accept` endpoint) spawns a `MissionInstance` from
`template.mission_template` via `staff_assign_mission` (the board-take
primitive). Missions' `_finish_terminal` calls `resolve_task_for_mission`
(mirroring the crisis seam): the terminal route's outcome tier grades into
the SAME `TaskOutcomeRoute` table — one authored payout surface, two
execution engines. No risk pool on the PC path. Abandoned/expired missions
fail their task via the hourly sweep.
