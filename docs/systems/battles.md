# Battles

Large-scale battle scenes (war covenant engagements, sieges, pitched-field fights)
resolved through abstract round-based mechanics. A `Battle` is a 1:1 extension of
`scenes.Scene` — mirroring the `Covenant` ↔ `Organization` pattern — so the full scene
infrastructure (GM, participation, privacy) applies without duplication.

**Issue:** #1592 (PR 1 — playable spine).

## Architecture

A `Battle` auto-creates a backing `Scene` on first save (`Battle.save()` wraps the
creation in `transaction.atomic()`; never use `bulk_create`). The GM runs the battle
through the scene; players enlist and declare actions each round, each declaration naming
a `Technique` the character actually knows. The resolution engine casts that technique
through the real magic envelope (`use_technique`, via `resolve_battle_technique`) and
routes failures through `process_damage_consequences` (the same path as tactical combat).
Victory points accumulate on each `BattleSide` until one side meets its threshold or the
round limit expires.

`BattleRoundContext` plugs into the shared `get_active_round_context` seam, so a player
in an active battle gets a `BattleRoundContext` when the dispatcher looks for their round
context — the same seam that returns a `CombatRoundContext` for combat participants.

## Models

All models use `SharedMemoryModel` from `evennia.utils.idmapper.models`.

### `Battle`

1:1 extension of `scenes.Scene` (OneToOneField, CASCADE, `related_name="battle"`).

| Field | Type | Notes |
|---|---|---|
| `scene` | O2O → `scenes.Scene` | Auto-created in `save()`; never set manually |
| `name` | CharField(120) | Human-readable name |
| `campaign_story` | FK → `stories.Story` (null) | Optional parent campaign story |
| `round_limit` | PositiveSmallIntegerField | Default 10; auto-concludes at expiry |
| `outcome` | CharField | `BattleOutcome` choice; default UNRESOLVED |
| `concluded_at` | DateTimeField (null) | Timestamp when concluded |
| `afk_peril_override` | BooleanField | Default False; when True, Surrounded peril escalates every round regardless of declaration (#1733, see ADR-0074) |
| `created_at` | DateTimeField (auto) | |

**Properties:**
- `is_concluded` — `outcome != BattleOutcome.UNRESOLVED`
- `current_round` — latest non-COMPLETED `BattleRound`, or None

### `BattleSide`

One side in a battle (attacker or defender) with its victory-point tally.

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="sides"`) | |
| `role` | CharField | `BattleSideRole` — ATTACKER / DEFENDER |
| `victory_points` | PositiveIntegerField | Accumulates each round |
| `victory_threshold` | PositiveIntegerField | Default 100; how many VP to win |

**Constraint:** unique `(battle, role)` — one attacker and one defender per battle.

### `BattlePlace`

A named front or zone within a battle (e.g. "The Main Gates", "Eastern Flank").

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="places"`) | |
| `name` | CharField(120) | Human-readable front name |
| `combat_encounter` | FK → `combat.CombatEncounter` (null) | Bridge seam: a discrete tactical combat at this front |

**Constraint:** unique `(battle, name)`.

### `BattleUnit`

An abstract typed force (enemy or friendly) stationed at a front.

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="units"`) | |
| `side` | FK → `BattleSide` (`related_name="units"`) | |
| `place` | FK → `BattlePlace` (null) | Optional front assignment |
| `name` | CharField(120) | Display name (e.g. "Cavalry") |
| `unit_type` | CharField(80) | Descriptive type tag (e.g. "zombies-on-nightmares") |
| `strength` | PositiveSmallIntegerField | Default 100; decremented by STRIKE successes |
| `status` | CharField | `BattleUnitStatus` — ACTIVE / ROUTED / DESTROYED |

Strength is decremented by `success_level × STRIKE_ATTRITION_PER_LEVEL` (10 per level).
A unit at strength 0 becomes DESTROYED; strength ≤ 30 (`ROUTED_STRENGTH_THRESHOLD`) becomes
ROUTED.

### `BattleRound`

Subclasses `world.scenes.round_models.AbstractRound` (which provides `round_number`,
`status`, `round_started_at`, `completed_at`).

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="rounds"`) | |

**Constraint:** unique active round per battle — at most one round in DECLARING,
RESOLVING, or BETWEEN_ROUNDS status at a time (partial unique constraint).

### `BattleParticipant`

A player character enlisted in a battle on one side.

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="participants"`) | |
| `character_sheet` | FK → `character_sheets.CharacterSheet` (`related_name="battle_participations"`) | |
| `side` | FK → `BattleSide` (`related_name="participants"`) | |
| `place` | FK → `BattlePlace` (null) | Optional front assignment |
| `status` | CharField | `BattleParticipantStatus` — ACTIVE / WITHDRAWN / INCAPACITATED |

**Constraint:** unique `(battle, character_sheet)`.

### `BattleActionDeclaration`

A participant's declared action for one round.

| Field | Type | Notes |
|---|---|---|
| `battle_round` | FK → `BattleRound` (`related_name="declarations"`) | |
| `participant` | FK → `BattleParticipant` (`related_name="declarations"`) | |
| `technique` | FK → `magic.Technique` (`related_name="battle_declarations"`) | The technique cast for this declaration; required |
| `action_kind` | CharField | `BattleActionKind` — STRIKE / SUPPORT / RESCUE (#1733) |
| `target_unit` | FK → `BattleUnit` (null) | Strike target |
| `target_ally` | FK → `BattleParticipant` (null, `related_name="support_declarations"`) | Support target, or the Surrounded ally being rescued (RESCUE, #1733) |
| `resolved` | BooleanField | False until the GM resolves the round |
| `success_level` | SmallIntegerField | Check success level; >0 = success, ≤0 = failure |

**Constraint:** unique `(battle_round, participant)` — one declaration per participant
per round. Participants may redeclare (the service uses `update_or_create`).

## Round Flow

### `BattleRoundContext`

`src/world/battles/round_context.py`

Implements the `RoundContext` ABC and plugs into `actions.round_context.get_active_round_context`
(inserted after the combat branch, before the scene branch). The resolver queries for the
character's ACTIVE `BattleParticipant` whose `battle.scene.is_active=True`, ordered by
`-battle__created_at` (most recent wins in the rare edge case of multiple active battles).

| Property / Method | Behaviour |
|---|---|
| `round_id` | `(battle_id, round_number)` — `(battle_id, 0)` when no active round |
| `is_declaration_open` | True when current round status is DECLARING |
| `is_repeat_blocked(actor, action_ref, target_persona)` | True when declaration window is not open |
| `record_declaration(character, player_action, kwargs)` | Writes a `BattleActionDeclaration` via `update_or_create` |

### `resolve_battle_technique` + `BattleTechniqueResolver` (`src/world/battles/resolution.py`)

`resolve_battle_technique(*, declaration) -> CheckResult | None` casts `declaration.technique`
through the real magic envelope (`world.magic.services.use_technique`) rather than a generic
shared check. Routing through `use_technique` means the check is sourced from the caster's
actual technique (`technique.action_template.check_type`), anima cost / Soulfray accumulation
apply normally, and the Audere / Audere Majora escalation hook fires automatically (it's
wired inside `use_technique` itself — no separate battle-side call site is needed).
`confirm_soulfray_risk=True` because a batch round-resolve cannot pause mid-batch for one
participant's consent prompt. Returns `None` (treated as `success_level=0`, a failure) if the
cast is interrupted before resolution (e.g. a reactive PRE_CAST cancellation).

`BattleTechniqueResolver` is the `resolve_fn` dataclass passed to `use_technique`; its
`__call__` rolls the declared technique's own check via `perform_check` — battle applies no
damage-profile/condition logic of its own, that stays in `resolve_battle_round`'s
STRIKE/SUPPORT/failure routing below.

### `resolve_battle_round` (`src/world/battles/resolution.py`)

Iterates all unresolved `BattleActionDeclaration` rows for the round and for each:

1. Calls `resolve_battle_technique(declaration=declaration)` to cast the declared technique.
2. **On `success_level > 0`:**
   - STRIKE: decrements `target_unit.strength` by `success_level × STRIKE_ATTRITION_PER_LEVEL`;
     upgrades unit status to ROUTED or DESTROYED at thresholds;
     adds `success_level × STRIKE_VP_PER_LEVEL` to the participant's side.
   - SUPPORT: adds `SUPPORT_VP` (3) to the participant's side.
   - RESCUE: clears the target ally's Surrounded condition (#1733, no VP awarded — see
     [Peril / Rescue](#peril--rescue-1733) below).
3. **On `success_level ≤ 0`:** debits PC health by `BASE_FAILURE_DAMAGE + abs(success_level)`;
   calls `process_damage_consequences(character_sheet, damage_dealt, damage_type=None, source_character=None)`
   (non-progressive; SQLite-safe); rolls the Surrounded entry pool if the participant is
   isolated (#1733, see below).
4. Marks each declaration `resolved=True`, stores `success_level`.
5. Sets `battle_round.status = COMPLETED`.

Returns a `BattleRoundResult` dataclass:
- `vp_awarded: dict[int, int]` — VP gained per side pk this round
- `units_destroyed: list[int]` — destroyed unit pks
- `units_routed: list[int]` — routed unit pks
- `casualties: list[int]` — participant pks who took damage

## Peril / Rescue (#1733)

Isolated participants can be cut off and swarmed — a staged "Surrounded" acute-peril
condition, generalizing the same guarded-consequence-pool machinery Bleeding-Out uses
(#1479 / ADR-0049), specialized for battles. See ADR-0074 for the AFK-safety exception
this introduces.

### The "Surrounded" condition (`world/vitals/factories.py::ensure_surrounded_content`)

Idempotently seeds a `ConditionTemplate` named `SURROUNDED_CONDITION_NAME` ("Surrounded",
`world/conditions/constants.py`) with `has_progression=True` and 3 `ConditionStage` rows,
each resisted with the existing Endurance `CheckType` (the same survivability semantic
Bleeding-Out already uses):

| Stage order | Name | `resist_difficulty` |
|---|---|---|
| 1 | Encircled | 15 |
| 2 | Overwhelmed | 25 |
| 3 | Being Cut Down | 35 |

It also seeds 3 `ConsequencePool` rows (natural keys in `world/vitals/constants.py`):

| Pool name | Used by | Outcomes |
|---|---|---|
| `POOL_SURROUNDED_ENTRY` (`surrounded_entry`) | Entry roll | success/partial → `no_effect`; failure → `surrounded` |
| `POOL_SURROUNDED_TERMINAL_ENEMY` (`surrounded_terminal_enemy`) | Terminal stage, non-PC isolating side | success → `recover`; partial → `stay_incapacitated`; failure → `die` (`character_loss=True`) |
| `POOL_SURROUNDED_TERMINAL_PVP` (`surrounded_terminal_pvp`) | Terminal stage, PC isolating side | success → `recover`; partial → `stay_incapacitated`; **no `die` row at all** (ADR-0023 — structurally non-lethal, not filtered-at-resolution) |

### Entry roll (`world/battles/resolution.py::_maybe_apply_surrounded`)

Called from `_resolve_failure` on every check failure. Only proceeds when
`_is_isolated(participant)` is True — no other ACTIVE `BattleParticipant` on the same
side shares the participant's `place` (a participant with `place=None` is never
isolated — front-agnostic, not alone at a front). Isolation and mobility are objective,
code-computed signals fed as `extra_modifiers` into the roll — the pool's authored rows
decide the actual odds, never a hardcoded gate:

- `SURROUNDED_ENTRY_ISOLATED_MODIFIER = -15` — always applied when isolated.
- `SURROUNDED_ENTRY_MOBILITY_MODIFIER = 40` — added when
  `_has_unimpaired_mobility(character_sheet)` is True (resolved via
  `get_effective_capability_value` against `FoundationalCapability.MOVEMENT`, the same
  way `can_act` resolves AWARENESS — not the room-based positioning-graph fields, which
  don't apply to location-less battles).

The roll is dispatched through `select_consequence` against the entry stage's
`resist_check_type` / `resist_difficulty` with those `extra_modifiers`; if the selected
consequence's label is `"surrounded"`, `apply_condition(target=character,
condition=template)` applies the condition — the `has_progression=True` template
auto-initializes `current_stage` to stage 1.

### Per-round escalation tick (`world/battles/resolution.py::_advance_surrounded_participants`, `world/vitals/services.py::advance_surrounded`)

`resolve_battle_round` calls `_advance_surrounded_participants(battle_round.battle,
declared_participant_ids)` once per round, after routing all declarations and before
marking the round `COMPLETED`. For each ACTIVE `BattleParticipant` in the battle: the
peril only advances if the participant declared this round, **or**
`battle.afk_peril_override` is True — otherwise it holds unchanged (mirrors the intent
of the room-based `#1480`/ADR-0047 own-peril skip without depending on `SceneRound`).

`advance_surrounded(character_sheet, *, battle)` is a thin wrapper around the shared
`_advance_staged_peril_condition` helper (also used by `advance_bleed_out`): each
non-terminal stage rolls its authored resist check, advancing to the next stage on
failure; the terminal stage (stage 3, "Being Cut Down") hands off to
`resolve_surrounded_terminal`.

### Terminal routing (`world/battles/resolution.py::select_surrounded_terminal_pool`, `resolve_surrounded_terminal`)

`select_surrounded_terminal_pool(*, battle, participant)` routes to
`surrounded_terminal_pvp` when an ACTIVE opposing `BattleParticipant` with a real PC
character (`character_sheet__character__db_account__isnull=False`) is present at the
same `place` (ADR-0023 — PvP stays non-lethal), else to `surrounded_terminal_enemy`
(the isolating pressure is normally an abstract, non-PC `BattleUnit`, so death is
reachable). `resolve_surrounded_terminal` finds the character's `BattleParticipant`,
routes the pool, computes `death_permitted = not has_death_deferred(character)`, and
dispatches through the shared `_resolve_peril_via_pool` core (`world/vitals/services.py`
— the same death-gated resolution used by Bleeding-Out and abandonment). On death, the
participant's `status` is set to `INCAPACITATED`.

### Rescue (`BattleActionKind.RESCUE`, `world/battles/resolution.py::_resolve_rescue_success`)

`RESCUE` is a third `BattleActionKind`, declared the same way as SUPPORT — via
`declare_battle_action(action_kind=RESCUE, target_ally=<participant>, technique=...)`,
reusing the `target_ally` FK (see the docstring note in `services.py`). On
`success_level > 0`, `resolve_battle_round` calls `_resolve_rescue_success` instead of
the STRIKE/SUPPORT handlers: it clears the target ally's active Surrounded condition via
`remove_condition`, if any. No VP is awarded — rescue trades round economy for saving an
ally, not battlefield progress. No-op (not an error) if the target ally isn't currently
Surrounded. Telnet: `battle declare rescue <ally> with <technique>` (`CmdBattle`,
`src/commands/battle.py`).

### `Battle.afk_peril_override`

`BooleanField`, default `False`. When `True`, a Surrounded participant's peril escalates
every round the GM resolves regardless of whether they declared — a narrow, explicit
exception to ADR-0004 scoped to peril only (see **ADR-0074**).

## Stakes / Beat Wiring (#1785)

`world.battles.beat_wiring` wires a concluded `Battle` into the same
`record_outcome_tier_completion` seam #1746 built for `CombatEncounter` —
reusing the stakes-contract engine (`world.stories.services.stakes`,
`world.stories.services.stake_resolution`) as-is.

### `BattleOutcomeMapping`

A designer-authored map from `BattleOutcome` to a `traits.CheckOutcome` tier
(`outcome` unique, `check_outcome` nullable FK). Unlike combat's
`EncounterOutcomeMapping`, there's no separate risk-level axis —
`BattleOutcome`'s four values already encode decisive-vs-marginal severity.
Starts empty; a missing row or a null `check_outcome` resolves to
`PENDING_GM_REVIEW`. Admin-registered (`world/battles/admin.py`).

### `classify_battle_conclusion_outcome(battle) -> CheckOutcome | None`

Looks up the `BattleOutcomeMapping` row for `battle.outcome`. Raises
`ValueError` if called before the battle has a graded outcome.

### `activate_stakes_for_battle(battle) -> None`

Called from `begin_battle_round` the first time a battle opens round 1.
Collects every currently-`ACTIVE` `BattleParticipant`'s character sheet
(no-ops if none), and for each staked `UNSATISFIED` beat linked to
`battle.scene` (via `staked_unsatisfied_beats_for_scene`,
`world.stories.services.stakes`), boundary-screens it
(`check_stake_boundaries`) and locks it with
`activate_stakes_contract(beat, sheets, scale_by_party_level=False)`.

**`scale_by_party_level=False`**: a war's stakes reflect the objective being
fought over, not which specific PCs happen to be enlisted — unlike
scene-level stakes (ADR-0077), Battle activation skips the
party-level-gap-adjusted `compute_effective_risk` entirely; a ready contract
prices at its declared risk unconditionally. See **ADR-0080**.

### `resolve_battle_beats(battle) -> None`

Called directly from `conclude_battle` — not via a flow event/`TriggerDefinition`
like combat's `ENCOUNTER_COMPLETED` wiring, since `Battle` has no location
(`Battle.scene.location` is `None`, per #1733) and `conclude_battle` is already
the single call-site choke point for battle conclusion. Finds every
`UNSATISFIED` `OUTCOME_TIER` beat linked to `battle.scene` (identical
`Scene → EpisodeScene → Episode → Beat` discovery to combat's wiring),
classifies `battle.outcome` once, and resolves every linked beat to that same
tier (one `Battle` grades as one outcome, applied uniformly — per-front
independent grading is **#1760**'s job, not duplicated here). No `withdrawal`
path: `BattleOutcome` has no FLED/ABANDONED-equivalent value.

## Services (`src/world/battles/services.py`)

All public functions are the only permitted entry points for battle state mutations.
Multi-write operations use `@transaction.atomic`.

| Service | Signature | Effect |
|---|---|---|
| `create_battle` | `(*, name, campaign_story=None, round_limit=DEFAULT_ROUND_LIMIT) -> Battle` | Creates Battle + backing Scene |
| `add_side` | `(*, battle, role, victory_threshold=DEFAULT_VICTORY_THRESHOLD) -> BattleSide` | Adds a side |
| `add_place` | `(*, battle, name) -> BattlePlace` | Adds a named front |
| `add_unit` | `(*, battle, side, name, unit_type, strength=100, place=None) -> BattleUnit` | Adds an abstract unit |
| `enlist_participant` | `(*, battle, character_sheet, side, place=None) -> BattleParticipant` | Enlists a PC |
| `begin_battle_round` | `(*, battle) -> BattleRound` | Closes prior round (→ COMPLETED) and opens a new DECLARING round. Raises `BattleConcludedError` if already concluded. |
| `declare_battle_action` | `(*, participant, action_kind, technique, target_unit=None, target_ally=None) -> BattleActionDeclaration` | Records or updates the participant's action declaration for the current DECLARING round. Raises `RoundNotOpenError` if no DECLARING round, `CharacterDoesNotKnowTechniqueError` if the character doesn't know `technique`, `TechniqueNotBattleReadyError` if `technique` has no `action_template`. |
| `check_victory` | `(*, battle) -> BattleOutcome \| None` | Returns the graded outcome if any side has reached its threshold, else None. Decisive if margin ≥ `DECISIVE_MARGIN` (50). |
| `conclude_battle` | `(*, battle, outcome) -> Battle` | Sets outcome + `concluded_at`; ends the backing scene (`is_active=False`); resolves any linked story beat's stakes contract via `resolve_battle_beats` (#1785). Does NOT call `complete_story` — a war arc spans multiple battles, so one battle's conclusion must not auto-close the whole campaign story. Idempotent. |
| `maybe_conclude_on_timer` | `(*, battle) -> BattleOutcome \| None` | Fires when no active round exists and `completed_round_count >= round_limit`. Timeout rule: defender holds unless attacker meets threshold. |

## Actions (`src/actions/definitions/battles.py`)

Four REGISTRY actions, all registered in `src/actions/registry.py`:

| Key | Class | target_type | Who | Effect |
|---|---|---|---|---|
| `begin_battle_round` | `BeginBattleRoundAction` | AREA | GM / staff | Opens a new DECLARING round |
| `resolve_battle_round` | `ResolveBattleRoundAction` | AREA | GM / staff | Resolves current round; auto-concludes if `check_victory` fires |
| `conclude_battle` | `ConcludeBattleAction` | AREA | GM / staff | Force-concludes; tries natural win → timer → DEFENDER_MARGINAL default |
| `declare_battle_action` | `DeclareBattleActionAction` | SELF | Player | Records a STRIKE, SUPPORT, or RESCUE declaration (with `technique_id`) for the current round |

GM actions are gated by `_actor_may_gm_battle` (staff or `battle.scene.is_gm(account)`).
The active battle in the actor's room is resolved by `_active_battle_in_room` (newest
non-concluded battle whose `scene.location` matches the actor's room).

`BattleError` subclasses surface as `ActionResult(success=False, message=exc.user_message)`.

## Telnet: `CmdBattle` (`src/commands/battle.py`)

Key: `battle`. Registered in the default cmdset. No business logic in the command.

| Subverb | Effect |
|---|---|
| `battle` | Show caller's active battle status (battle name, side VP, front, current round) |
| `battle declare strike <unit> with <technique>` | Declare STRIKE against a named ACTIVE unit, casting a known technique |
| `battle declare support <ally> with <technique>` | Declare SUPPORT for an allied participant, casting a known technique |
| `battle declare rescue <ally> with <technique>` | Declare RESCUE for a Surrounded ally, casting a known technique (#1733) |
| `battle round` | GM: begin the next round |
| `battle resolve` | GM: resolve the current round |
| `battle conclude` | GM: force-conclude the battle |

Unit names are resolved case-insensitively within the caller's active battle. Ally names
are resolved by `character.db_key` case-insensitively. Technique names are resolved
case-insensitively against the caller's known `CharacterTechnique` rows
(`_resolve_technique`); an unknown name raises `CommandError`. `CommandError` is raised for
bad usage; `_send(result)` routes the `ActionResult.message` back to the caller.

## Enums / Constants (`src/world/battles/constants.py`)

| Name | Kind | Values |
|---|---|---|
| `BattleSideRole` | TextChoices | ATTACKER / DEFENDER |
| `BattleUnitStatus` | TextChoices | ACTIVE / ROUTED / DESTROYED |
| `BattleParticipantStatus` | TextChoices | ACTIVE / WITHDRAWN / INCAPACITATED |
| `BattleActionKind` | TextChoices | STRIKE / SUPPORT / RESCUE (#1733) |
| `BattleOutcome` | TextChoices | UNRESOLVED / ATTACKER_DECISIVE / ATTACKER_MARGINAL / DEFENDER_MARGINAL / DEFENDER_DECISIVE |

**Tuning constants:**
- `DEFAULT_VICTORY_THRESHOLD = 100`
- `DEFAULT_ROUND_LIMIT = 10`
- `STRIKE_ATTRITION_PER_LEVEL = 10`
- `STRIKE_VP_PER_LEVEL = 5`
- `SUPPORT_VP = 3`
- `BASE_FAILURE_DAMAGE = 8`
- `DECISIVE_MARGIN = 50`
- `ROUTED_STRENGTH_THRESHOLD = 30`
- `SURROUNDED_ENTRY_ISOLATED_MODIFIER = -15` — entry-roll signal (#1733), isolated at a place
- `SURROUNDED_ENTRY_MOBILITY_MODIFIER = 40` — entry-roll signal (#1733), unimpaired MOVEMENT capability

## Exceptions (`src/world/battles/exceptions.py`)

- `BattleError(Exception)` — base; carries `user_message`
  - `BattleConcludedError` — operation on already-concluded battle
  - `RoundNotOpenError` — declaration outside a DECLARING round
  - `NotAParticipantError` — character not enlisted in the battle
  - `CharacterDoesNotKnowTechniqueError` — participant declared a technique they don't know
  - `TechniqueNotBattleReadyError` — declared technique has no `action_template` (not castable)

## Legend / Outcome Model and Stakes Wiring (#1785)

`Battle.outcome` stores the graded result (`BattleOutcome`), and `Battle.campaign_story`
(FK → `stories.Story`, null) holds the optional parent campaign story — informational
metadata only, not used for beat resolution (see below). `conclude_battle` deliberately
**does not** call `complete_story` — automatically closing the whole campaign story on
one battle's conclusion would foreclose a war arc prematurely.

Campaign-stakes propagation (battle outcome → Story + win-gated Legend) is wired via
`world.battles.beat_wiring` (#1785) — see [Stakes / Beat Wiring](#stakes--beat-wiring-1785)
below.

## PR 1 Scope vs. Deferred

**Built in PR 1 (#1592):** full battle lifecycle (stage → enlist → declare → resolve
→ conclude); round flow with VP accumulation and unit attrition; graded outcomes; timer
rule; `BattleRoundContext` seam; telnet `CmdBattle`; E2E journey test
(`integration_tests/pipeline/test_battle_telnet_e2e.py`).

**Built as a follow-up spine (real-technique-cast dispatch, #1734):** `technique` is now a
required FK on `BattleActionDeclaration`; `declare_battle_action` validates the participant
knows the technique and that it's castable (`action_template` set);
`resolve_battle_round` casts each declaration's technique through the real magic envelope
(`resolve_battle_technique` → `use_technique`) instead of a generic shared `CheckType` —
anima cost, Soulfray accumulation, and the Audere / Audere Majora escalation hook all apply
exactly as they would for any other cast. The generic `"Battle Action"` `CheckType` /
`BATTLE_CHECK_TYPE_NAME` / `get_battle_check_type()` seam has been removed entirely.

**Deferred to follow-up issues:**

| What | Issue |
|---|---|
| Battle writeup / React page | #1735 |
| Rich unit type-matchups (cavalry vs. infantry modifiers) | #1711 |
| Command hierarchy, naval / aerial / siege variants | #1710, #1713, #1714 |
| Campaign propagation: battle outcome → Story + win-gated Legend | **Shipped in #1785** — see [Stakes / Beat Wiring](#stakes--beat-wiring-1785) |

Peril / rescue and the AFK knob are no longer deferred — see
[Peril / Rescue (#1733)](#peril--rescue-1733) below.

## Test Coverage

- `src/world/battles/tests/test_constants.py` — enum smoke tests
- `src/world/battles/tests/test_models.py` — model save + side/unit relationships
- `src/world/battles/tests/test_round_context.py` — `get_active_round_context` wiring
- `src/world/battles/tests/test_services_setup.py` — create/enlist/begin-round lifecycle
- `src/world/battles/tests/test_resolution.py` — `resolve_battle_technique` /
  `BattleTechniqueResolver` unit test; STRIKE success (unit attrition + VP) and failure
  (PC health debit) with `world.battles.resolution.perform_check` patched (the check inside
  `use_technique`'s cast, not a bypass of it)
- `src/world/battles/tests/test_conclusion.py` — `check_victory` grading and
  `conclude_battle` (confirms `complete_story` is NOT called)
- `src/world/battles/tests/test_actions.py` — each action's `run()` path; GM-gate rejection
- `src/world/battles/tests/test_command.py` — telnet `battle declare strike <unit>` path,
  including `test_declare_rescue_dispatches_rescue_action_kind` (#1733)
- `src/integration_tests/pipeline/test_battle_telnet_e2e.py` — full GM-stages → PCs
  declare → GM resolves (check mocked) → unit attrition + PC damage → VP over threshold →
  GM concludes → `battle.is_concluded` and scene ended
- `src/world/battles/tests/test_resolution.py` (#1733) —
  `IsolationAndMobilityTests` (`_is_isolated` / `_has_unimpaired_mobility`),
  `SelectSurroundedTerminalPoolTests` (enemy vs. pvp routing),
  `EntryRollTests` (isolated failure applies Surrounded via the entry pool,
  `@tag("postgres")`), `EscalationTickTests` (declared-this-round vs.
  `afk_peril_override` gating), `RescueResolutionTests` (RESCUE clears Surrounded)
- `src/world/vitals/tests/test_peril_pools.py::EnsureSurroundedContentTests` (#1733) —
  idempotent seeding of the condition + its 3 stages + 3 pools
- `src/world/vitals/tests/test_services.py::AdvanceStagedPerilTests` — regression pin for
  the `_advance_staged_peril_condition` extraction shared by `advance_bleed_out` and
  `advance_surrounded` (#1733 Task 3)
- `src/integration_tests/pipeline/test_battle_peril_rescue_e2e.py`
  (`BattlePerilRescueE2EJourneyTest`, #1733) — two telnet journeys: isolated STRIKE
  failure → Surrounded entry → AFK-driven escalation (`afk_peril_override`) → successful
  RESCUE clears it (`@tag("postgres")`); and terminal-stage resolution routing to the
  death-permitting enemy pool vs. the death-free PvP pool (ADR-0023)
- `src/world/battles/tests/test_beat_wiring.py` (#1785) — `BattleOutcomeMapping`
  model constraints, `classify_battle_conclusion_outcome`, `activate_stakes_for_battle`
  wiring + `scale_by_party_level=False`, `conclude_battle` → beat/stake resolution
  integration

## Integrates With

- **Scenes** — `Battle` extends `scenes.Scene`; scene GM-check gates GM actions;
  `is_active` / `date_finished` written by `conclude_battle`
- **Character Sheets** — `BattleParticipant.character_sheet` FK
- **Vitals** — `process_damage_consequences` on check failure; the shared
  `_resolve_peril_via_pool` core (`world.vitals.services`) resolves the Surrounded
  terminal stage the same way it resolves Bleeding-Out and abandonment (#1733)
- **Conditions** — the "Surrounded" staged `ConditionTemplate` + its 3 `ConditionStage`
  rows, seeded by `world.vitals.factories.ensure_surrounded_content`; applied/removed via
  `apply_condition` / `remove_condition` (#1733)
- **Magic** — `BattleActionDeclaration.technique` FK; `resolve_battle_technique` routes
  each declaration's cast through `world.magic.services.use_technique` (anima cost,
  Soulfray, Audere / Audere Majora escalation all apply)
- **Checks** — `perform_check`, sourced from the cast technique's
  `action_template.check_type` (via `use_technique`), not a generic battle-wide `CheckType`;
  the Surrounded entry roll and per-round resist checks are dispatched through
  `world.checks.consequence_resolution.select_consequence` against authored
  `ConsequencePool` rows (#1733)
- **Combat** — `BattlePlace.combat_encounter` bridge seam (for discrete tactical fights
  at a front); `RoundStatus` and `AbstractRound` shared from `world.scenes`
- **Stories** — `Battle.campaign_story` FK (informational; not used for beat
  resolution); `world.battles.beat_wiring` resolves linked `Beat`s via
  `Scene → EpisodeScene → Episode` (#1785)
- **Actions** — four REGISTRY actions, `BattleRoundContext` in `get_active_round_context`

## Source

`src/world/battles/`
- `models.py` — all battle models
- `constants.py` — enums + tuning constants
- `services.py` — all service functions (setup + declaration + conclusion)
- `resolution.py` — `resolve_battle_round` + `BattleRoundResult`
- `round_context.py` — `BattleRoundContext` + `resolve_battle_round_context`
- `exceptions.py` — exception hierarchy
- `factories.py` — FactoryBoy factories for all models

`src/actions/definitions/battles.py` — four REGISTRY actions

`src/commands/battle.py` — `CmdBattle` telnet namespace
