# Covenants

Magically-empowered group oaths with roles, gear compatibility, a per-covenant rank
ladder, and (as of #1165) a Mentor's Vow bond system for level-mismatched parties.

**Standing invariant:** `CovenantRole` = combat power (archetype, speed_rank, Thread
pulls). `CovenantRank` = administrative authority (invite/kick/manage). These two
axes are orthogonal — never re-merge them.

## Models

### Core covenant models

- **`CharacterCovenantRole`** — per-character membership row; `left_at IS NULL` =
  currently active. Fields include `covenant` FK, `covenant_role` FK, `engaged`
  boolean, `rank` FK → `CovenantRank`.
- **`GearArchetypeCompatibility`** — existence-only join: which `CovenantRole`s are
  compatible with which `GearArchetype` values (read-only authored content).
- **`CovenantRole`** sub-role fields — a sub-role is a `CovenantRole` with a non-null
  `parent_role` (self-FK) and `resonance` (FK → `magic.Resonance`). Additional fields:
  - `unlock_thread_level` (PositiveIntegerField, default 0 for primary roles; >0 for
    sub-roles) — the COVENANT_ROLE thread level a character must reach to manifest this
    sub-role variant.
  - `discovery_achievement` (FK → `achievements.Achievement`, nullable) — sub-roles only;
    the achievement granted (with a global-first `Discovery` row) on first threshold crossing.
  - `codex_entry` (FK → `codex.CodexEntry`, nullable) — sub-roles only; the lore entry
    unlocked (`CharacterCodexKnowledge(KNOWN)`) on threshold crossing.
- **`CovenantRoleBonus`** — authored config: one row per `(CovenantRole, ModifierTarget)`
  with `bonus_per_level` SmallInt. `role_base_bonus_for_target(role, target,
  char_level)` returns `char_level × bonus_per_level`; no row → 0. Admin-registered.
- **`VowStatScaling`** (#2022) — authored config: one row per
  `(CovenantRole, ModifierTarget)` with `bonus_per_level` scaling by the
  **COVENANT_ROLE thread level** (not character level, which `CovenantRoleBonus`
  already handles). `vow_stat_scaling_bonus(sheet, target)` returns
  `thread_level × bonus_per_level`; no row → 0. The mechanical heart of "solo
  darkness" — a deepened vow is a substantially stronger character. When the vow
  dims (#2051), the scaling drops to 0.
- **`VowGearScaling`** (#2022) — authored config: one row per
  `(gear_archetype, role_archetype)` with a `thread_level_multiplier` (Decimal).
  Amplifies how much equipped gear contributes: the bonus is
  `int(gear_stat × thread_level × multiplier)`. Extends
  `GearArchetypeCompatibility` from a gate (which gear you can use) to a
  multiplier (how much it contributes). When the vow dims, the equipment's
  contribution reverts to base.
- **`ArchetypeActionScaling`** (#2022) — authored config: one row per
  `(action_key, role_archetype)` with a `thread_level_multiplier` (Decimal).
  Read by `archetype_action_scaling_bonus(character, action_key)` at the combat
  action resolution seam. SHIELD roles scale the interpose partial-block damage
  reduction; SWORD roles add a flat power bonus to `cast_technique` via a power
  term provider; CROWN roles scale rally actions.
- **`CovenantRoleGiftGrant`** (#2022) — through model for
  `CovenantRole.granted_gifts` M2M to `magic.Gift`. Carries
  `unlock_thread_level` — the COVENANT_ROLE thread level at which the gift's
  techniques become available while engaged (0 = always while engaged).
- **`CovenantRole.granted_capabilities`** (#2022) — M2M to
  `conditions.CapabilityType`. Read directly by `passive_capability_grants()`
  in `handlers.py` alongside the existing `ThreadPullEffect`-based capability
  grants. Capabilities apply while the role is engaged; drop automatically when
  the vow dims.
- **`CovenantRank`** — per-covenant administrative authority tier. Fields: `covenant`
  FK (CASCADE, `related_name="ranks"`), `name` (max 60, player-chosen), `tier`
  (PositiveInt; 1 = top authority), `description`, `can_invite` bool, `can_kick` bool,
  `can_manage_ranks` bool. Unique `(covenant, tier)` and `(covenant, name)`. Ordered by
  `["covenant", "tier"]`.

### Mentor's Vow models (#1165)

- **`MentorBondConfig`** (pk=1 singleton) — global parameters for Mentor's Vow
  scaling. Fields:
  - `band_width` (PositiveSmallInt, default 2) — level-range half-width for eligible
    mentor/sidekick pairs. The covenant band is `[covenant.level − band_width,
    covenant.level + band_width]`.
  - `adjacency_offset` (PositiveSmallInt, default 1) — additional level offset applied
    when computing the adjusted party's effective level.
  - `max_sidekicks_per_mentor` (PositiveSmallInt, nullable; null = unlimited) — cap on
    active bonds per mentor per covenant.
  - `updated_at` / `updated_by` — audit timestamps. Seeded via
    `seed_mentor_bond_defaults()` in factories.py; staff-tunable in Django admin.

- **`MentorBond`** — one active bond record per (covenant, sidekick_sheet) pair (via
  partial unique constraint `unique_active_sidekick_bond`). Dissolved bonds are retained
  as an audit trail. Fields:
  - `covenant` FK (CASCADE, `related_name="mentor_bonds"`)
  - `mentor_sheet` FK → `CharacterSheet` (`related_name="mentor_bonds_as_mentor"`)
  - `sidekick_sheet` FK → `CharacterSheet` (`related_name="mentor_bonds_as_sidekick"`)
  - `adjusted_party` CharField (`MentorBondAdjusted.MENTOR` / `SIDEKICK`) — records
    which party the level adjustment is applied to.
  - `formed_at` DateTimeField (auto)
  - `dissolved_at` DateTimeField (null = still active; set on dissolution)
  - Custom manager method: `.active()` → filters `dissolved_at__isnull=True`.

## Handlers

- `character.covenant_roles` (`CharacterCovenantRoleHandler`):
  - `has_ever_held(role)` — True if the character has ever held this role (active or ended).
  - `currently_held_role_in(covenant)` — active role in the specified covenant, or None.
  - `currently_engaged_roles()` — list of **resolved (effective) roles** for every
    active+engaged membership. Calls `resolve_effective_role` per row: if the character's
    COVENANT_ROLE thread qualifies for a resonance sub-role, the sub-role is returned instead
    of the parent. Consumers that must key on the stored anchor identity should use
    `anchor_role_in()` instead.
  - `anchor_role_in(covenant)` — returns the **stored parent (anchor) role** for the active
    membership in `covenant`, ignoring sub-role resolution. Use this when the consumer must
    key on the thread's `target_covenant_role_id` or the raw membership row.
  - `invalidate()` — clear the cached assignment list; called by mutator services.

## Key Services

### Resonance sub-role resolution

- **`resolve_effective_role(*, character, role) -> CovenantRole`** (`world.covenants.services`) —
  derive-on-read. Given a primary role, walks the character's COVENANT_ROLE threads and finds the
  highest-qualifying resonance sub-role (highest `unlock_thread_level` the thread has crossed).
  Returns `role` unchanged when no qualifying sub-role exists, or when `role` is already a
  sub-role (single-depth; no re-promotion). Called per-row by `currently_engaged_roles()`.

- **`fire_subrole_discoveries(*, thread, starting_level, new_level) -> None`**
  (`world.covenants.discovery`) — fired by `spend_resonance_for_imbuing` after every COVENANT_ROLE
  thread imbue. For each sub-role whose `unlock_thread_level` was newly crossed (i.e.,
  `starting_level < unlock_thread_level <= new_level`):
  - Grants `discovery_achievement` via `grant_achievement` (creates a global-first `Discovery` row
    when this is the first ever earner).
  - Unlocks `codex_entry` via `CharacterCodexKnowledge.objects.get_or_create(status=KNOWN)`,
    keyed on `roster_entry`.
  - Sends a `NarrativeMessage(category=COVENANT)`: gamewide to all `active_player_character_sheets()`
    on first-ever discovery; personal to the discovering sheet otherwise.
  - Idempotent: an already-existing `CharacterAchievement` row gates the whole beat (no duplicates
    on replay).

### Core covenant services

- `assign_covenant_role(sheet, role) -> CharacterCovenantRole`
- `end_covenant_role(role_assignment) -> None`
- `kick_member(*, target, actor) -> None` — actor's rank must have `can_kick=True`
  and `actor.rank.tier < target.rank.tier` (lower tier = higher authority); raises
  `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError`
- `is_gear_compatible(role, archetype) -> bool` — existence-only join lookup
- `role_base_bonus_for_target(role, target, char_level) -> int` (in
  `world.mechanics.services`) — reads `CovenantRoleBonus`; returns
  `char_level × bonus_per_level`; 0 if no row
- **Rank management** — all require `actor.rank.can_manage_ranks=True`:
  `create_rank`, `rename_rank`, `set_rank_capabilities`, `reorder_ranks`,
  `delete_rank`, `assign_rank`, `transfer_top`. Lock-out invariant:
  `LastManagerRankError` if an op would leave zero active managers.

### Mentor's Vow services (`world.covenants.mentorship`)

- **`covenant_band(covenant) -> tuple[int, int]`** — returns `(low, high)` inclusive
  level band `[covenant.level − band_width, covenant.level + band_width]`.
- **`is_in_band(covenant, raw_level) -> bool`** — True if raw_level is within the band.
- **`active_bond_adjusting(sheet) -> MentorBond | None`** — returns the active,
  non-graduated bond where `sheet` is the adjusted party; None if absent, dissolved,
  or graduated.
- **`bond_adjusted_level(sheet) -> int | None`** — returns the adjusted effective level
  when an active non-graduated bond reshapes `sheet`; None otherwise.
- **`effective_combat_level(sheet) -> int`** — the bond-adjusted combat level. When an
  active non-graduated bond exists, returns the adjusted level; otherwise returns the
  raw primary class level via `get_character_path_level`. This is what
  `compute_party_profile` calls per participant — outlier distortion is absorbed here.

  Adjustment rule:
  - **SIDEKICK adjusted**: `effective = clamp(mentor_raw − adjacency_offset, band)`
  - **MENTOR adjusted**: `top` = max raw primary level over all active MENTOR-adjusted
    sidekick bonds (one bulk query); `effective = clamp(top + adjacency_offset, band)`
  - **Graduated** (adjusted party's raw primary level is already in band) → treated as
    inactive → returns raw primary level.

- **`is_bond_graduated(bond) -> bool`** — True when the adjusted party's raw primary
  level has re-entered the covenant band (bond is mechanically inactive).
- **`establish_mentor_bond(*, covenant, mentor_sheet, sidekick_sheet) -> MentorBond`** —
  atomically determines `adjusted_party` (exactly one must be out of band), enforces the
  `max_sidekicks_per_mentor` cap (counts all active bonds where this character is the
  mentor in this covenant), and creates the `MentorBond`. Raises `MentorBondError` on
  constraint violations.
- **`dissolve_mentor_bond(bond) -> None`** — sets `dissolved_at = now()`.
- **`assert_membership_level_allowed(*, covenant, character_sheet) -> None`** — the
  **Vow gate**. Raises `VowGateError` if the character's raw primary level is outside
  the covenant band AND they have no active bond (as mentor or sidekick) in this
  covenant. Called by `add_member`; `create_covenant` (formation) is ungated. Gate is
  inactive when `MentorBondConfig` has not been seeded.

### Mentor's Vow ritual service

- **`establish_mentor_bond_via_session(*, session: RitualSession) -> MentorBond`** —
  the service function wired to `MentorsVowRitualFactory` (in `world.magic.factories`).
  The ritual is a consensual BILATERAL_SERVICE ritual; the session's leader and
  co-performer are the two bond parties. Unpacks the session, identifies which
  participant is mentor vs. sidekick based on band position, and calls
  `establish_mentor_bond`.

## Telnet Surface

### CmdCovenant (`covenant`, #1346)

`src/commands/covenant.py` — one `ArxCommand` routes a leading subverb to the matching
covenant Action via `action.run()`, sharing the same service layer as the web viewsets.

| Subverb | Action key | Effect |
|---|---|---|
| `covenant [list]` | — | List the caller's memberships (hub) |
| `covenant engage [<covenant>]` | `engage_covenant_membership` | Engage a role for the current scene |
| `covenant disengage [<covenant>]` | `disengage_covenant_membership` | Disengage a role |
| `covenant leave [<covenant>]` | `leave_covenant` | Voluntarily end membership |
| `covenant kick <char> [in <covenant>]` | `kick_covenant_member` | Rank-gated removal |
| `covenant rank <char> <rank> [in <covenant>]` | `assign_covenant_rank` | Promote/demote a member |
| `covenant transfer <char> [in <covenant>]` | `transfer_covenant_top_rank` | Transfer the top rank |
| `covenant standdown [<covenant>]` | `stand_down_battle_covenant` | Return a risen STANDING Battle covenant to dormancy |

Supply the covenant name when the character belongs to more than one. `standdown` is STANDING
Battle covenants only; `engage`/`disengage` are gated by the same `can_engage_membership` logic
the web uses. `CovenantError` subclasses surface as `ActionResult(success=False)` with a
`user_message`.

### Induction and Banner-Call Rise via CmdRitual

Covenant **induction** (adding a new member) and the **banner-call rise** (raising a dormant
STANDING Battle covenant) are session-driven ceremonies that go through `CmdRitual` with
adapter-dispatched token parsing (`src/commands/ritual_adapters.py`):

**Induction:**
1. Initiator: `ritual draft "Covenant Induction" invite=<char> covenant=<name>` — drafts a
   session; the `CovenantInductionAdapter` emits a session-level COVENANT reference.
2. Inductee: `ritual join <id> role=<covenant role name>` — the adapter emits a COVENANT_ROLE
   reference the induction service reads to assign the role.
3. Initiator: `ritual fire <id>` — calls `induct_member_via_session`, which creates the
   `CharacterCovenantRole` row.

**Banner-call rise:**
1. Initiator: `ritual draft "Call the Banners" invite=<char>[,<char>] covenant=<name>` —
   `BannerCallAdapter` emits a session-level COVENANT reference; no join tokens are required.
2. Members: `ritual join <id>` — simply accept (no role kwargs needed).
3. Initiator: `ritual fire <id>` — calls `rise_battle_covenant_via_session`, which flips the
   covenant risen and auto-engages all accepted participants.

### Selectors (`world.covenants.selectors`)

`src/world/covenants/selectors.py` — shared read-only lookups used by the covenant viewsets
and the Actions (one copy, not two):

- `resolve_actor_membership(*, covenant, character_sheets, capability=None) -> CharacterCovenantRole | None`
  — first active membership in `covenant` among `character_sheets` that carries `capability`
  (a rank flag such as `can_kick` or `can_manage_ranks`), or any active membership if `None`.
- `get_active_memberships(*, character_sheet) -> list[CharacterCovenantRole]`
  — all active (`left_at IS NULL`) memberships for one character sheet, with related covenant,
  rank, and covenant_role pre-fetched.

## Induction Round-Trip

The covenant induction flow is wired end-to-end through the UI:

1. **Draft** — initiator opens `RitualSessionDraftDialog`; the COVENANT reference is
   set so `assert_initiator_can_induct` can validate the initiator's rank at draft time.
2. **Candidate accepts with role** — `RitualSessionResponseDialog` renders the
   `candidate_only` `CovenantRolePickerField` (from `input_schema.participant_fields`),
   resolves the COVENANT reference from `session.session_references` to populate the
   role picker's `covenant_type` filter, and converts the `emits_reference: "COVENANT_ROLE"`
   field value into a typed `RitualSessionReference` in the accept request's `references`
   array.
3. **Initiator fires** — `POST /api/magic/ritual-sessions/{id}/fire/` dispatches the
   induction service function, which reads the COVENANT_ROLE reference and calls
   `assign_covenant_role` to create the `CharacterCovenantRole` row.

**Test coverage:** `RitualInductionRoundTripTests`
(`src/world/magic/tests/test_session_views.py`) covers the full draft → accept-with-role
→ fire → `CharacterCovenantRole` created backend path. Frontend component tests in
`frontend/src/rituals/__tests__/RitualSessionPages.test.tsx` cover the role-picker
rendering, `emits_reference` → `references` conversion on accept, and `candidate_only`
field hiding for the initiator.

## Covenant of the Court (#1589)

A `CovenantType.COURT` covenant models a single powerful master and the servants/apprentices sworn
to them across a ≥1-tier power gulf. See ADR-0057 (amended 2026-06-30) for the design rationale.

### Model additions

- **`Covenant.leader`** — FK → `character_sheets.CharacterSheet` (`null=True`,
  `on_delete=SET_NULL`, `related_name="led_courts"`). Required for COURT, forbidden for other
  types (enforced in `Covenant.clean()`). The structural analogue of `campaign_story` on Battle
  covenants. An NPC master is an account-less `CharacterSheet` seated as the `is_leader` founder.

- **`CourtPact`** — per-(Court, servant) sworn-fealty bond.
  - `covenant` FK (PROTECT, `related_name="court_pacts"`)
  - `servant_sheet` FK → `CharacterSheet` (PROTECT, `related_name="court_pacts"`)
  - `granted_pull_cap` (PositiveSmallIntegerField) — master-set ceiling on the servant's
    Court-role thread pull level. A servant with no active pact has an effective cap of 0 and
    cannot pull their Court-role thread.
  - `sworn_at` (auto DateTimeField), `released_at` (null = still active)
  - Partial-unique constraint `uniq_court_pact_active`: at most one active pact per
    `(covenant, servant_sheet)`. Released pacts are retained as an audit trail.
  - Custom queryset: `.active()` → `released_at__isnull=True`.

### Services (`world.covenants.services`)

- **`swear_court_pact(*, covenant, servant_sheet, granted_pull_cap) -> CourtPact`** — creates an
  active pact. Raises `CourtPactExistsError` if an active pact already exists for the pair.
- **`release_court_pact(*, pact) -> None`** — soft-releases by setting `released_at = now()`.
- **`active_court_pact_for(*, covenant, servant_sheet) -> CourtPact | None`** — returns the single
  active pact or `None`.

### Gulf enforcement (`world.covenants.mentorship`)

`assert_membership_level_allowed` (COURT arm) enforces the ≥1 power-tier gulf before a servant
may join. Uses `power_tier_for_level(level) -> int` (`world/covenants/power_tier.py`): levels
1–5 → tier 1, 6–10 → tier 2, 11–15 → tier 3, etc. (band width = `TIER_ONE_MAX_LEVEL` = 5).
Raises `CourtGulfViolationError` if `power_tier_for_level(servant) >= power_tier_for_level(leader)`.
This check runs before the `MentorBondConfig` gate so it fires even without a seeded config.

### Mission-driven engagement (`world.covenants.court_missions`)

`has_active_court_mission(*, character_sheet, covenant) -> bool` — single `.exists()` query;
True iff the character participates in an ACTIVE `MissionInstance` whose
`source_offer.role.faction_affiliation_id` matches `covenant.organization_id`. A `NULL`
`source_offer` (legacy/staff-seeded runs) never matches — correct behavior.

`can_engage_membership` (COURT branch in `world/covenants/handlers.py`) gates engagement on this
predicate. `_auto_engage_court` in `services.py` auto-engages newly inducted Court servants when
the predicate is satisfied. Battle covenants use `not is_dormant` as their gate; the Court
mission-gate is new dedicated machinery.

### Continuous vow enforcement (#2051)

`revalidate_engagements(*, character_sheet, room)` in `services.py` re-runs
`can_engage_membership` for each engaged `CharacterCovenantRole`. On failure,
`clear_engaged_membership` dims the vow (max health recompute + cache flush) and
emits a notice: "Your vow dims — the covenant is not with you." COURT vows
re-validate by their own arm (master's business stays lit); BATTLE re-checks
dormancy only.

Wired into two departure seams:
- **`move_object`** (`flows/service_functions/movement.py`): captures the origin
  room before the move, then revalidates the mover at the destination AND each
  remaining origin-room occupant with an engaged covenant role (hot-path
  short-circuit: skips occupants with no engaged role — no DB query).
- **`finish_scene_full`** (`scenes/scene_admin_services.py`): invalidates the
  room's active-scene cache (the scene is no longer active) and revalidates
  remaining occupants — Durance vows dim when the scene they were tied to ends.

Auto-engage on next qualifying arrival already exists, so power relights the
moment the covenant reunites.

### Pull-cap enforcement (`world.magic.services.threads`)

`compute_anchor_cap` delegates to `_bound_covenant_role_cap_by_court_grant` for
`TargetKind.COVENANT_ROLE` threads on COURT covenants. This bounds the anchor cap by the
servant's `granted_pull_cap` from the active `CourtPact`. No pact → cap 0 → the grant is the gate.

### Grant negotiation (#1718)

`granted_pull_cap` is no longer fixed at swearing-in. Two channels raise it:

- **Formal petition** — a new `OfferKind.COURT_GRANT` offer (auto-provisioned per
  Court via `world.covenants.court_grant.ensure_court_grant_role`, which is
  `@transaction.atomic` with a `select_for_update()` re-fetch of the `Covenant`
  row so two concurrent negotiation attempts for the same Court can't both pass
  the "role not yet provisioned" check), riding the existing
  `NPCServiceOffer`/effect-handler pipeline. The effect handler
  (`world.npc_services.effects.raise_court_grant`) rolls a shared "Court Grant
  Petition" check (eased by the master's `NPCStanding.affection`) and, on
  success, raises the grant up to `court_grant_ceiling(...)` via
  `raise_court_pact_grant`, which is strictly monotonic
  (`CourtGrantNotMonotonicError` on any attempted decrease; raising to the
  current cap is a harmless no-op).
- **Emergency thread-bond draw** — not a standalone Action. It's an optional
  `beseech=<n>` token on the existing `cast`/`clash` pull-declaration grammar
  (`commands/combat.py`), resolved by the shared, combat-agnostic
  `_resolve_emergency_draw(sheet, cast_pull)` helper
  (`world.combat.pull_helpers`). That helper is called from both the in-combat
  path (`commit_combat_pull`) and the non-combat immediate-cast path
  (`world.magic.services.techniques._charge_cast_pull`), so the draw works
  whether or not the master is in the scene. **Web (non-telnet) support does
  not exist** — `world/scenes/action_serializers.py::_validate_cast_pull` →
  `world.combat.pull_helpers.build_cast_pull_declaration` has no
  `beseech_bonus` parameter; only the telnet grammar parses `beseech=`.
  The requested bonus is clamped to `min(requested_bonus,
  court_grant_ceiling(...) + CourtGrantConfig.emergency_draw_max_bonus)` — the
  config field bounds how far the draw may exceed the ceiling, not the raw
  bonus — for one pull only, never persisted to `Thread.level`, at the cost of
  debt on any amount past the ceiling.

`court_grant_ceiling(*, covenant, servant_sheet) -> int`
(`world.covenants.court_grant`) = `base_headroom + affection // affection_divisor
+ completed_court_mission_count // mission_divisor - outstanding_debt(...)`,
floored at 0, all tunable via the `CourtGrantConfig` singleton
(`get_court_grant_config()`).

Debt and the consecutive-failed-petition streak generalize onto `NPCStanding`
(`world.npc_services`), not `CourtPact` — `NPCStanding.debt` /
`debt_baseline_affection` / `debt_baseline_missions_completed` /
`consecutive_failed_petitions`, plus the generic services
`incur_npc_debt`/`outstanding_debt`/`record_petition_outcome`
(`world.npc_services.services`) — so any future "petition an NPC" feature can
reuse the same substrate. `consecutive_failed_petitions` crossing
`CourtGrantConfig.petition_failure_escalation_threshold` fires
`CourtGrantConfig.escalation_consequence_pool` (a standard `ConsequencePool`,
same machinery as trap/clash/stakes resolution).

Pull-effect scaling by thread level (`thread_level_multiplier`,
`world.magic.services.threads`) was corrected alongside this feature: level 0
keeps the old floor of `Decimal(1)`; levels 1–9 now ramp linearly from 0.1 to
1.0 (`Decimal(level) / Decimal(10)`) instead of sitting flat at the old
floor — levels 1–9 score *below* the old flat-1.0 floor, a deliberate
tradeoff so a thread crossing the level-10 milestone doesn't score worse than
level 9 did; level ≥ 10 is unchanged (`Decimal(level // 10)`).

See ADR-0085 for why the debt/streak fields live on `NPCStanding` rather than `CourtPact`.

### Directed-offer summonses — the master's wishes (#2050)

A Court master (or any NPC role) can direct a mission offer at a *specific*
servant via an `OfferSummons` (`world.npc_services.summons`). The servant sees
the summons in their journal and can accept (delegating to `resolve_offer` →
`issue_mission`, with court engagement + grant-ceiling credit flowing as today)
or decline. Declining — or letting the summons lapse — drops affection
(`SUMMONS_REFUSAL_AFFECTION_DELTA`) and bumps
`NPCStanding.consecutive_refused_summons`; crossing
`CourtGrantConfig.summons_refusal_escalation_threshold` fires the master's
escalation pool via `apply_pool_deterministically` (the no-check precedent).
Debt is never the price of disobedience — ADR-0102.

Creation is GM/staff-driven (web API + mid-scene "Give mission" dialog). The
expiry cron (`npc_services.summons_expiry`, 5-minute sweep) treats timeout as a
refusal. See ADR-0102 for the full design.

### Fealty ceremony

`induct_member_via_session` (the ritual fire-handler) was extended for COURT covenants: after
creating the `CharacterCovenantRole`, it calls `swear_court_pact` with `granted_pull_cap` read
from `participant_kwargs` and emits a servant-spotlight narration alongside the induction message.

### Exceptions (added in `world.covenants.exceptions`)

- `CourtGulfViolationError` — servant's power tier is not strictly below the leader's.
- `CourtPactExistsError` — an active pact already exists for `(covenant, servant_sheet)`.
- `CourtGrantNotMonotonicError` — a grant raise would lower an existing `CourtPact.granted_pull_cap` (#1718).

### Test coverage

`src/world/covenants/tests/integration/test_court_e2e.py` — full E2E journey: create Court,
induct servant (gulf enforced), swear pact, mission-driven engage, pull-cap bounded, dissolve
(last servant leaves → Court auto-dissolves).

## Enums / Constants

- **`MentorBondAdjusted`** (`TextChoices` in `world.covenants.constants`) —
  `MENTOR` / `SIDEKICK`: which party the encounter-scaling adjustment is applied to.

## Combat Seams

### Role bonuses (#985)

`apply_equipped_armor_soak` adds `_covenant_armor_soak_bonus` (armor-soak
`ModifierTarget` total) on top of raw soak; `_weapon_augmented_budget` adds
`_combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)` to technique budget. Both
route through `get_modifier_total` → `covenant_role_bonus` equipment walk.

In combat, the covenant role bonus reads the **bond-adjusted level** rather than the
raw primary level: `_combat_target_bonus(sheet)` calls `bond_adjusted_level(sheet)` and
passes the result as `level_override` through `get_modifier_total` →
`equipment_walk_total` → `covenant_role_bonus`. A suppressed mentor's role bonus
shrinks; an elevated sidekick's bonus grows.

### Encounter scaling (#1165)

`compute_party_profile` (in `world/combat/scaling.py`) calls `effective_combat_level`
per ACTIVE participant before averaging. Level-outlier distortion is absorbed into the
bond math; the #566 invariant (difficulty keys off level and party size only, never
threads/relationships/covenants/facets/fashion) is preserved.

Graduation: when the adjusted party's real primary level re-enters the band,
`effective_combat_level` returns the raw level and the bond is dissolved at
`begin_declaration_phase`.

## Exceptions (`world.covenants.exceptions`)

- `CovenantRoleNeverHeldError` (Thread weave gate)
- `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError` (kick service)
- `NotAuthorizedToManageRanksError`, `LastManagerRankError`, `CrossCovenantRankError`,
  `IncompleteRankReorderError`, `CannotTransferToDepartedMemberError` (rank management)
- `MentorBondError` (bond creation / cap enforcement)
- `VowGateError` (membership level gate: `add_member` refused)

## API Endpoints

- `GET /api/covenants/gear-compatibilities/` — read-only authored content
- `GET /api/covenants/character-roles/` — read-only; non-staff scoped to own
  currently-played sheets; exposes nested `rank` + `viewer_capabilities`.
  `CharacterCovenantRoleSerializer` fields:
  - `covenant_role` — the **resolved (effective) sub-role** when the character's thread has
    crossed a sub-role threshold; otherwise the stored parent role. Derive-on-read via
    `resolve_effective_role`.
  - `anchor_role` — the **stored parent (anchor) role** on the membership row, ignoring
    sub-role resolution. Consumers that need to key on thread identity use this field.
- `GET|POST /api/covenants/ranks/` — list / create ranks
- `GET|PATCH|DELETE /api/covenants/ranks/{pk}/` — retrieve / update / delete
- `POST /api/covenants/ranks/reorder/` — bulk tier reorder
- `POST /api/covenants/ranks/{pk}/assign-member/` — assign member to rank
- `POST /api/covenants/ranks/{pk}/transfer-top/` — move top rank to member

## Follow-ups

- **Health scaling (#1256)** — `max_health` is not currently level-derived (it is
  `base_max_health + thread_addend`); Path-level-driven health is deferred to #1256.
- **Abyssal master/apprentice display labels** — the Mentor's Vow mechanic is flavor-neutral
  in the model layer. Thematic display labels (e.g. "Abyssal master/apprentice") are a
  future display-label layer with no model surface in v1.
- **Graduation auto-dissolve** — `begin_declaration_phase` dissolves graduated bonds;
  a separate async/background path for non-combat graduation is a follow-up.
- **Court deferred items** — the convince-the-master economy, enemy-of-master substrate,
  per-instance authored roles, and active capability surge were deliberately NOT built in #1589;
  they are follow-up design items.

## Integrates With

- Magic (`COVENANT_ROLE` Thread anchor cap = `current_level × 10`, bounded for COURT roles by
  `CourtPact.granted_pull_cap` via `_bound_covenant_role_cap_by_court_grant`; `MentorsVowRitualFactory`;
  `spend_resonance_for_imbuing` hooks `fire_subrole_discoveries` after each imbue)
- Missions (`has_active_court_mission` queries `MissionInstance` + `NPCServiceOffer` + `NPCRole`
  + `faction_affiliation` to gate COURT engagement)
- Mechanics (`covenant_role_bonus` in modifier walk; `level_override` via `bond_adjusted_level`)
- Items (`gear_archetype` on `ItemTemplate`)
- Combat (`apply_equipped_armor_soak` + `_weapon_augmented_budget`; `compute_party_profile`
  via `effective_combat_level`)
- Achievements (`CovenantRole.discovery_achievement` FK; `grant_achievement` on sub-role
  threshold crossing; `Discovery` row created on first-ever earner)
- Codex (`CovenantRole.codex_entry` FK; `CharacterCodexKnowledge(status=KNOWN)` created per
  roster_entry on threshold crossing)
- Narrative (`send_narrative_message(category=COVENANT)` for gamewide / personal discovery
  announcements; `active_player_character_sheets()` from `world.roster.selectors` selects
  gamewide recipients on first-ever discovery)

## Source

`src/world/covenants/`

- `models.py` — all covenant + mentor bond + CourtPact models
- `handlers.py` — `CharacterCovenantRoleHandler`; `currently_engaged_roles()` calls
  `resolve_effective_role` (defined in `services.py`) per row; `can_engage_membership` (COURT arm)
- `services.py` — covenant lifecycle + `resolve_effective_role` + `establish_mentor_bond_via_session`
  + `swear_court_pact` / `release_court_pact` / `active_court_pact_for` + `induct_member_via_session`
  (extended for COURT)
- `selectors.py` — `resolve_actor_membership` / `get_active_memberships`; shared by viewsets
  and the covenant Actions
- `discovery.py` — `fire_subrole_discoveries` (sub-role discovery beat)
- `mentorship.py` — `effective_combat_level` and Mentor's Vow math; `assert_membership_level_allowed`
  (COURT gulf arm)
- `court_missions.py` — `has_active_court_mission` (mission-driven engagement predicate)
- `power_tier.py` — `power_tier_for_level` (gulf enforcement helper)
- `factories.py` — `seed_resonance_subrole_slice`, `SubroleCovenantRoleFactory`
- `exceptions.py` — all exceptions

`src/actions/definitions/covenants.py` — seven covenant lifecycle REGISTRY Actions

`src/commands/covenant.py` — `CmdCovenant` telnet namespace

`src/commands/ritual_adapters.py` — `SoulTetherAdapter`, `CovenantInductionAdapter`,
`BannerCallAdapter` + `get_adapter(ritual)` registry lookup
