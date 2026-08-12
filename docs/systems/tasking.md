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
  (`{task}`/`{target}`/`{agent}` format kwargs), nullable `collection_success_level`
  (set ⇒ this route lands the issuing org's `currency.collect_org_income` graded at
  that level, handler as collector; null ⇒ no collection — #696 item 2, see
  "Domain collection" below), plus the Spy Job Kit payout fields (below). No route
  for a tier ⇒ nothing happens (fail closed).
- **`OrgTask`** — live instance: `template`, `org`, `issued_by` persona, `status`
  (`TaskStatus`: OPEN→ASSIGNED→RESOLVING→COMPLETED/FAILED/EXPIRED), `deadline`
  (set at assignment), target via `DiscriminatorMixin` (`target_kind` selects
  exactly one of room/org/domain/persona/crisis; NONE ⇒ all null).
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

## Spy Job Kit (`spy_payouts.py`, #2833)

Route-level payout flags applied by `apply_spy_payouts` (called from
`resolve_task` via `_apply_route_payouts`); each degrades to a report line on a
missing/mismatched target, never an exception:

- `movements_report` (PERSONA) — where the mark has been seen: scene
  `Interaction` rows in PUBLIC rooms only, last `MOVEMENTS_REPORT_DAYS` days.
  Mechanical residue, never prose (ADR-0175).
- `unmask_target` (PERSONA) — pierce a mask: mints/loads the pair
  `PERSONA_LINK` clue and grants it to the handler (`PersonaDiscovery`).
- `gossip_heat_delta` (PERSONA, ±) — amplify or quash the hottest existing
  `SecretGossip` row about the mark. Never mints dirt — whisper campaigns need
  something real (or an accusation) to fan.
- `building_condition_delta` (ROOM, ±) — sabotage/repair via
  `set_condition_tier` on buildings in the room's area.
- `recruit_target` (PERSONA) — suborn an NPC into an org-held `NPCAsset`;
  refuses PCs (tenure check) — PC recruitment stays consensual RP.
- `incriminate_level` — the residue rule: sloppy-tier routes mint a
  GM-provenance (TRUE) `Secret` about the **handler** plus an investigable
  counter-clue trail in the region's hubs. Never confessed in the report.
- **Cross-system addendum**: `domain_report` (DOMAIN — population, prosperity,
  unrest, holdings, open crises), `domain_unrest_delta` (DOMAIN, ± clamp
  0–100 — foment or soothe; feeds the weekly domain tick/crisis machinery),
  `organization_report` (ORG — member count, treasury *band* never exact coin,
  own-agent count, parent/wings), `military_report` (ORG — persistent
  `MilitaryUnit` counts + active armies; troop *movements* wait on positional
  military state).
- **Threat-loop counterplay (#2837, ADR-0177)**: `reveal_schemes` (ORG/DOMAIN —
  mints `CrisisIntel` for the issuing org on still-covert generated crises;
  on your own org also names active hostile tasks aimed at you —
  counter-intelligence), `crisis_severity_delta` (CRISIS target — negative
  counters a step, resolving below trouble as TASK_COMPLETED; positive
  inflames), `exploit_crisis` (CRISIS target — resolves EXPLOITED and pays
  the issuing org the magnitude boon via `apply_crisis_boon`). `OrgTask`
  gains the `TaskTargetKind.CRISIS` discriminator leg (`target_crisis`).

Consent: `template_is_offensive` classifies routes; offensive jobs refuse at
ISSUE time (`TargetConsentError`) when the target is a PC — or a PC-led org /
domain (owner org's `can_manage_ranks` members' tenures) — who hasn't opted
into the `espionage` category. Defensive templates (quash-only, soothe-only)
and NPC targets are ungated.

Seeds: `world/seeds/spy_tasks.py` (`spy_tasks` cluster) — fourteen
PLACEHOLDER templates (incl. Sweep for Schemes / Counter the Scheme / Fan the
Flames / Seize the Opening) + the "Spywork Exposure" risk pool (ASSET_STATUS
COMPROMISED). The crisis catalog itself is the `crisis_types` cluster
(`world/seeds/crisis_types.py`).

## API (`views.py`, `/api/tasking/`)

- `templates/`, `routes/` — staff authoring CRUD (`IsAdminUser`).
- `tasks/` — the member board: list/retrieve scoped to the active persona's org
  memberships (non-member ⇒ empty, per IC-reads-scope-to-active-character);
  `POST tasks/` leader-gated (`IsOrgLeaderForCreate` → `is_org_leader`);
  `POST tasks/{id}/assign/` any active member dispatching their own asset.
  Reports serialize only after resolution. Fulfillments reach the serializer via
  a context map on the list path — no `Prefetch` onto SharedMemoryModel parents.

## Frontend

`frontend/src/tasking/` — API client, queries, and `OperationsSection`
(Roster/Postings/Operations panels rendered on `OrgPage`, hidden when empty).

## Actions layer + telnet (`network` family)

Eleven REGISTRY actions in `actions/definitions/tasking.py` are the shared
seam (ADR-0001): `list_org_tasks`, `issue_org_task`, `assign_task_agent`,
`accept_org_task`, `post_listener`, `collect_harvest`, `suppress_listener`,
`flip_listener`, `plant_red_herring`, `detect_listeners`,
`clear_room_listeners`. The tasking viewsets dispatch through them (the web
no longer calls the services directly for mutations), and telnet reaches the
same actions via `CmdNetwork` (`network`, alias `spynet`,
`commands/network.py`): `network` (board), `issue <template> org=<org>`,
`assign <task-id> = <agent>`, `accept <task-id>`, `post <agent>`, `collect`,
`sweep`, `clear`, `suppress`, `flip`, `plant <post-id> <char> = <lie>`.
Location-contextual verbs act where the caller stands (the web passes
explicit `room_id`/`post_id` anchors); name→pk resolution is the only work
in the command.

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

## Domain collection (#696)

`TaskOutcomeRoute.collection_success_level` grades a task's issuing org
`currency.collect_org_income` dispatch: `_land_route_collection` calls
`collect_org_income(organization=task.org, character=handler_sheet.character,
success_level_override=route.collection_success_level)`, so the mission's
authored terminal outcome — not a second dice roll — decides how much of the
org's gathered pool lands (`currency.COLLECTION_BAND_PCTS`' own floors; below
the lowest floor is catastrophe, the pool is lost with the collector). A
`ValidationError` from an empty pool degrades to a report line, never a hard
task-resolution failure.

**Worked example** (`world/seeds/domain_tasks.py`, `domain_tasks` seed
cluster): "Collect the Levies" — a DOMAIN-target `TaskTemplate`
(`check_type=Tax Collection`, `check_difficulty` a static PLACEHOLDER pending
issue #696 item 8's unbuilt "steward's check sets difficulty" mechanic)
linked to a single-node CHECK `MissionTemplate` of the same name (RESTRICTED
visibility, no `availability_rule` — reachable ONLY via `accept_task`'s
`staff_assign_mission` call, never an open board). Each of the mission's
terminal `CheckOutcome` routes carries no mission-side MONEY reward (the
collector's cut lives on the linked `TaskOutcomeRoute` — one payout surface)
and grades `collection_success_level` straight off `COLLECTION_BAND_PCTS`'
own floors: Critical Success → 2 (110%), Success → 1 (100%), Partial Success
→ 0 (85%), Failure → -1 (35%, the smallest authored non-catastrophe band),
Critical Failure → -2 (below every floor ⇒ catastrophe). All prose and
tuning numbers are PLACEHOLDER pending Apostate's pass. End-to-end coverage:
`world/tasking/tests/test_collection_mission_e2e.py`.
