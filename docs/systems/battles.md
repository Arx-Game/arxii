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
| `covenant` | FK → `covenants.Covenant` (null, `related_name="battle_sides"`) | Optional War Covenant fielding this side (#1710) |
| `victory_points` | PositiveIntegerField | Accumulates each round |
| `victory_threshold` | PositiveIntegerField | Default 100; how many VP to win |
| `posture` | CharField | `BattlePosture` — BALANCED / AGGRESSIVE / DEFENSIVE (#1711); trades VP-gain speed against check difficulty and failure damage — see [Modifier Stack (#1711)](#modifier-stack-1711) |

**Constraint:** unique `(battle, role)` — one attacker and one defender per battle.

### `BattlePlace`

A named front or zone within a battle (e.g. "The Main Gates", "Eastern Flank").

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="places"`) | |
| `name` | CharField(120) | Human-readable front name |
| `combat_encounter` | FK → `combat.CombatEncounter` (null) | Bridge seam: a discrete tactical combat at this front |
| `terrain_type` | CharField | `TerrainType` — OPEN / DIFFICULT / FORTIFIED / ELEVATED / FLOODED / URBAN (#1711); default OPEN. See ADR-0081 for why terrain lives here rather than on the room `Position`/`PositionEdge` graph. |
| `movement_cost` | PositiveSmallIntegerField | Default 1 (#1711). Authored cost for a future reposition action (#1712) to consume — data only, no movement action exists yet. |

**Constraint:** unique `(battle, name)`.

### `BattleUnit`

An abstract typed force (enemy or friendly) stationed at a front.

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="units"`) | |
| `side` | FK → `BattleSide` (`related_name="units"`) | |
| `place` | FK → `BattlePlace` (null) | Optional front assignment |
| `name` | CharField(120) | Display name (e.g. "Cavalry") |
| `descriptor` | CharField(80), blank | Optional flavor tag (e.g. "zombies-on-nightmares"); narrative only — `composition`/`quality` below drive mechanics. Renamed from the spine's `unit_type` (#1711). |
| `composition` | CharField | `UnitComposition` — INFANTRY / CAVALRY / ARCHERS / SIEGE / FLYING / NAVAL / MAGICAL / IRREGULAR (#1711); default IRREGULAR. Drives type-matchup and terrain-effect lookups. |
| `quality` | CharField | `UnitQuality` — MILITIA / LEVY / TRAINED / VETERAN / ELITE (#1711); default TRAINED. Flat attacker-facing STRIKE-check modifier ladder, not a strength multiplier. |
| `commander` | FK → `character_sheets.CharacterSheet` (null, `related_name="commanded_battle_units"`) | Optional commander (#1711); their Battle Command modifier-walk bonus applies to participants fighting alongside this unit's side/place. |
| `summoned_by` | FK → `character_sheets.CharacterSheet` (null, `related_name="summoned_battle_units"`) | Set when this unit was created via a military-grade summon (#1711, see `_summon_military_unit`). |
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

### `TechniqueCompositionAffinity`

Authored `(technique, composition) → flat STRIKE-check modifier` row (#1711). Positive
means the technique is especially effective against that composition; negative means
weak against it.

| Field | Type | Notes |
|---|---|---|
| `technique` | FK → `magic.Technique` (PROTECT, `related_name="battle_composition_affinities"`) | |
| `composition` | CharField | `UnitComposition` value |
| `modifier` | SmallIntegerField | Signed flat check modifier |

**Constraint:** unique `(technique, composition)`.

Looked up by `BattleTechniqueResolver._composition_affinity_modifier` when a
declaration's `target_unit.composition` matches a row; returns 0 (no effect) when no
row matches — most techniques have no authored affinity.

### `TerrainCompositionEffect`

Authored `(terrain_type, composition) → flat attacker-facing STRIKE modifier` row
(#1711). Positive means that composition is easier to strike in that terrain; negative
means harder.

| Field | Type | Notes |
|---|---|---|
| `terrain_type` | CharField | `TerrainType` value |
| `composition` | CharField | `UnitComposition` value |
| `modifier` | SmallIntegerField | Signed flat check modifier |

**Constraint:** unique `(terrain_type, composition)`.

Looked up by `BattleTechniqueResolver._terrain_effect_modifier` against the target
unit's `place.terrain_type`; returns 0 when the unit has no place, or no row matches.

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

## Modifier Stack (#1711)

`BattleTechniqueResolver._battle_modifier_stack()` (`src/world/battles/resolution.py`)
sums five modifier sources into the `extra_modifiers` folded into the STRIKE check
rolled by `perform_check` inside `__call__`. Each source is independently 0 when it
doesn't apply — an unauthored technique/terrain combo, an unassigned commander, or a
BALANCED posture all contribute nothing:

| Source | Helper | Authored / looked up |
|---|---|---|
| Composition affinity | `_composition_affinity_modifier(technique, unit.composition)` | `TechniqueCompositionAffinity` row keyed on `(technique, target_unit.composition)`; 0 if none |
| Terrain effect | `_terrain_effect_modifier(unit.place, unit.composition)` | `TerrainCompositionEffect` row keyed on `(unit.place.terrain_type, unit.composition)`; 0 if the unit has no place or no row matches |
| Unit quality | `_quality_modifier(unit.quality)` | `UNIT_QUALITY_STRIKE_MODIFIER` dict in `constants.py` — a flat ladder from MILITIA (+10, easier to hit) to ELITE (−20, harder to hit) |
| Commander bonus | `commander_bonus_for_side_at_place(side, place)` | Max (not sum) `get_modifier_total` walk against the `"battle_command"` `ModifierTarget` (`ensure_battle_command_modifier_target`, seeded by `factories.py`) across every ACTIVE unit's `commander` on that side/place; 0 if none commanded |
| Posture | `BATTLE_POSTURE_CHECK_MODIFIER.get(participant.side.posture)` | `constants.py` dict — AGGRESSIVE −5, BALANCED 0, DEFENSIVE +10 |

The first three sources only apply to STRIKE declarations (they read `declaration.target_unit`,
which is `None` for SUPPORT/RESCUE); commander and posture apply to every declaration kind.
Posture also independently scales VP gain (`BATTLE_POSTURE_VP_MULTIPLIER`, applied in
`_resolve_strike_success`/`_resolve_support_success`) and failure damage
(`BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER`, applied in `_resolve_failure`) — those two scalings
are outside `_battle_modifier_stack()` (they don't affect the check roll itself) but are the
same posture-driven trade-off: AGGRESSIVE trades a −5 check penalty and +4 failure damage for
1.4× VP; DEFENSIVE trades +10 check ease and −4 failure damage for 0.7× VP.

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
| `add_side` | `(*, battle, role, victory_threshold=DEFAULT_VICTORY_THRESHOLD, covenant=None) -> BattleSide` | Adds a side, optionally fielded by a War Covenant (#1710) |
| `add_place` | `(*, battle, name, terrain_type=TerrainType.OPEN, movement_cost=1) -> BattlePlace` | Adds a named front (#1711: `terrain_type`/`movement_cost` kwargs) |
| `add_unit` | `(*, battle, side, name, descriptor="", composition=UnitComposition.IRREGULAR, quality=UnitQuality.TRAINED, commander=None, summoned_by=None, strength=100, place=None) -> BattleUnit` | Adds an abstract unit (#1711: `descriptor` replaces `unit_type`; adds `composition`/`quality`/`commander`/`summoned_by`) |
| `set_battle_side_posture` | `(*, side, posture) -> BattleSide` | Sets a side's `BattlePosture` (#1711) |
| `assign_unit_commander` | `(*, unit, commander) -> BattleUnit` | Assigns (or clears, with `commander=None`) a unit's commander (#1711) |
| `enlist_participant` | `(*, battle, character_sheet, side, place=None) -> BattleParticipant` | Enlists a PC |
| `begin_battle_round` | `(*, battle) -> BattleRound` | Closes prior round (→ COMPLETED) and opens a new DECLARING round. Raises `BattleConcludedError` if already concluded. |
| `declare_battle_action` | `(*, participant, action_kind, technique, target_unit=None, target_ally=None, scope=BattleActionScope.UNIT, target_place=None, target_side=None) -> BattleActionDeclaration` | Records or updates the participant's action declaration for the current DECLARING round. `scope`/`target_place`/`target_side` gate army/unit-scale declarations against command tier (#1710). Raises `RoundNotOpenError` if no DECLARING round, `CharacterDoesNotKnowTechniqueError` if the character doesn't know `technique`, `TechniqueNotBattleReadyError` if `technique` has no `action_template`, `NoCommandHierarchyError`/`InsufficientCommandTierError`/`MissingScopeTargetError`/`CannotStrikeOwnSideError` for scope violations. |
| `open_champion_duel` | `(*, battle_place, challenger_participant, opponent_kwargs, tier=OpponentTier.BOSS) -> CombatEncounter` | Binds `battle_place` to a new lethal duel (reuses `create_lethal_duel` unmodified) if the challenger holds an engaged Champion role (#1710). Raises `NotAChampionError`/`NoCommandHierarchyError`/`PlaceAlreadyDuelingError`. |
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

## Admin (`src/world/battles/admin.py`)

New file (#1711) — the shipped spine (#1592) had zero admin exposure. Registers every
battle model with a `ModelAdmin`: `Battle`, `BattleSide` (list-filtered on `role`/`posture`),
`BattlePlace` (list-filtered on `terrain_type`), `BattleUnit` (list-filtered on
`composition`/`quality`/`status`; `commander`/`summoned_by` as autocomplete fields),
`BattleRound`, `BattleParticipant`, `BattleActionDeclaration`, and the two new authored
catalogs `TechniqueCompositionAffinity` (list-filtered on `composition`; `technique` as an
autocomplete field) and `TerrainCompositionEffect` (list-filtered on
`terrain_type`/`composition`; no `technique` field), giving staff a CRUD surface to author
the type-matchup and terrain-effect content the modifier stack reads.

## Enums / Constants (`src/world/battles/constants.py`)

| Name | Kind | Values |
|---|---|---|
| `BattleSideRole` | TextChoices | ATTACKER / DEFENDER |
| `BattleUnitStatus` | TextChoices | ACTIVE / ROUTED / DESTROYED |
| `BattleParticipantStatus` | TextChoices | ACTIVE / WITHDRAWN / INCAPACITATED |
| `BattleActionKind` | TextChoices | STRIKE / SUPPORT / RESCUE (#1733) |
| `BattleOutcome` | TextChoices | UNRESOLVED / ATTACKER_DECISIVE / ATTACKER_MARGINAL / DEFENDER_MARGINAL / DEFENDER_DECISIVE |
| `UnitComposition` | TextChoices | INFANTRY / CAVALRY / ARCHERS / SIEGE / FLYING / NAVAL / MAGICAL / IRREGULAR (#1711) |
| `UnitQuality` | TextChoices | MILITIA / LEVY / TRAINED / VETERAN / ELITE (#1711) |
| `TerrainType` | TextChoices | OPEN / DIFFICULT / FORTIFIED / ELEVATED / FLOODED / URBAN (#1711) |
| `BattlePosture` | TextChoices | BALANCED / AGGRESSIVE / DEFENSIVE (#1711) |

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
- `UNIT_QUALITY_STRIKE_MODIFIER` — dict (#1711), flat attacker-facing STRIKE modifier per `UnitQuality`: MILITIA +10 … ELITE −20
- `BATTLE_POSTURE_VP_MULTIPLIER` — dict (#1711), percent VP-gain scaling per `BattlePosture`: AGGRESSIVE 1.4, BALANCED 1.0, DEFENSIVE 0.7
- `BATTLE_POSTURE_CHECK_MODIFIER` — dict (#1711), flat STRIKE-check modifier per `BattlePosture`: AGGRESSIVE −5, BALANCED 0, DEFENSIVE +10
- `BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER` — dict (#1711), flat failure-damage modifier per `BattlePosture`: AGGRESSIVE +4, BALANCED 0, DEFENSIVE −4
- `BATTLE_COMMAND_TARGET_NAME = "battle_command"` — idempotent-seed `ModifierTarget` name (#1711)
  for the commander-bonus walk, following the snake_case convention documented for
  stat-category modifier targets in `world/mechanics/CLAUDE.md`.

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

**Built as a follow-up spine (resources, units, terrain & tactics, #1711):** unit
composition/quality/commander taxonomy (`BattleUnit.composition`/`.quality`/`.commander`/
`.summoned_by`, replacing `unit_type` with the narrative-only `descriptor`); front
terrain (`BattlePlace.terrain_type`/`.movement_cost`); side tactical posture
(`BattleSide.posture`); the two new authored catalogs `TechniqueCompositionAffinity` and
`TerrainCompositionEffect`; the five-source [modifier stack](#modifier-stack-1711) folded
into every STRIKE check; Django admin for the whole app (`admin.py`, previously absent);
and an opt-in `summon_ally(payload.military=True)` branch that creates a `BattleUnit`
instead of a skirmish `CombatOpponent` (see [Integrates With](#integrates-with) below).

**Deferred to follow-up issues:**

| What | Issue |
|---|---|
| Battle writeup / React page | #1735 |
| Naval / aerial / siege variants | #1713, #1714 |

Peril / rescue and the AFK knob are no longer deferred — see
[Peril / Rescue (#1733)](#peril--rescue-1733) below. Rich unit type-matchups and terrain
effects are no longer deferred — see [Modifier Stack (#1711)](#modifier-stack-1711) above.
Campaign propagation (battle outcome → Story + win-gated Legend) is no longer deferred — see
[Stakes / Beat Wiring (#1785)](#stakes--beat-wiring-1785) below. Command hierarchy and the
Champion are no longer deferred — see
[Command Hierarchy & the Champion (#1710)](#command-hierarchy--the-champion-1710) below.

## Command Hierarchy & the Champion (#1710)

`CovenantRole.command_tier` (`NONE`/`SUBORDINATE`/`SUPREME`) and `.is_champion_role`
(bool) are settable only on `CovenantType.BATTLE` roles (`CovenantRole.clean()`).
Exclusivity — at most one engaged Supreme Commander and one engaged Champion per
covenant — is enforced in `CharacterCovenantRole.clean()` and
`world.covenants.services.set_engaged_membership`, structurally identical to the
existing character-scoped "one engaged role per covenant_type" check.

`BattleSide.covenant` (nullable FK -> `covenants.Covenant`) links a side to the War
Covenant fielding it; a side with no covenant has no command hierarchy. Command
permission is checked directly against `CharacterCovenantRole`/`command_tier` — not
routed through the `CapabilityType`/`ThreadPullEffect` engaged-gating mechanism (that
exists for condition-restricted capacities, a different domain).

`BattleActionDeclaration.scope` (`UNIT`/`PLACE`/`SIDE`) plus `target_place`/`target_side`
gate army/unit-scale declarations: `world.battles.services._validate_command_scope`
requires an engaged `SUBORDINATE`/`SUPREME` role for `PLACE`, `SUPREME` for `SIDE`, on
the side's covenant. `world.battles.resolution._resolve_strike_success` and
`_resolve_rescue_success` fan out across every active unit/participant at the scope
target instead of a single one.

The Champion duel reuses `world.combat.duels.create_lethal_duel` unmodified —
`world.battles.services.open_champion_duel` validates the challenger holds an engaged
`is_champion_role` `CovenantRole`, then binds the resulting `CombatEncounter` to the
`BattlePlace.combat_encounter` bridge seam (the first real caller of that seam since
#1592). Outcome feedback (rout/destroy the losing side's unit at that front, VP bonus
to the winner) is wired via `world.battles.duel_wiring`, mirroring
`world.combat.beat_wiring`'s `ENCOUNTER_COMPLETED` `TriggerDefinition` pattern exactly
— no new event type.

## Test Coverage

- `src/world/battles/tests/test_constants.py` — enum smoke tests
- `src/world/battles/tests/test_models.py` — model save + side/unit relationships;
  `BattleUnitTaxonomyTests` (composition/quality/commander/summoned_by/descriptor, #1711),
  `TechniqueCompositionAffinityTests`, `TerrainCompositionEffectTests` (#1711)
- `src/world/battles/tests/test_round_context.py` — `get_active_round_context` wiring
- `src/world/battles/tests/test_services_setup.py` — create/enlist/begin-round lifecycle;
  `AddUnitTests`, `AddUnitTaxonomyTests` (`add_unit`'s new taxonomy kwargs, #1711),
  `AddPlaceTerrainTests` (`add_place`'s `terrain_type`/`movement_cost` kwargs, #1711),
  `SetBattleSidePostureTests`, `AssignUnitCommanderTests` (#1711)
- `src/world/battles/tests/test_factories_seed.py` — `EnsureBattleCommandModifierTargetTests`
  (idempotent seeding of the `"battle_command"` `ModifierTarget`, #1711)
- `src/world/battles/tests/test_resolution.py` — `resolve_battle_technique` /
  `BattleTechniqueResolver` unit test; STRIKE success (unit attrition + VP) and failure
  (PC health debit) with `world.battles.resolution.perform_check` patched (the check inside
  `use_technique`'s cast, not a bypass of it); `CompositionAffinityModifierTests`,
  `TerrainEffectModifierTests`, `QualityModifierTests`, `CommanderBonusForSideAtPlaceTests`,
  `BattleTechniqueResolverModifierStackTests` (the full five-source stack), and
  `PostureVpScalingTests` (VP-gain and failure-damage posture scaling) (#1711)
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
- `src/world/magic/tests/test_summon_ally.py::SummonAllyMilitaryBranchTests` (#1711) —
  `payload.military=True` creates a `BattleUnit` (not a `CombatOpponent`) in the caster's
  active `Battle`; no-op when the caster has no ACTIVE `BattleParticipant`
- `src/world/battles/tests/test_beat_wiring.py` (#1785) — `BattleOutcomeMapping`
  model constraints, `classify_battle_conclusion_outcome`, `activate_stakes_for_battle`
  wiring + `scale_by_party_level=False`, `conclude_battle` → beat/stake resolution
  integration
- `src/world/battles/tests/test_resolution.py` (#1710) — SIDE-scope STRIKE fan-out
  across all units on a side; PLACE-scope RESCUE fan-out across all participants at
  a front
- `src/world/battles/tests/test_duel_wiring.py` (#1710) — Champion duel outcome
  auto-wiring: challenger victory routs the enemy unit at the bound place; a
  non-battle-bound encounter completion no-ops cleanly

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
  Soulfray, Audere / Audere Majora escalation all apply); `TechniqueCompositionAffinity.technique`
  FK (#1711). `world.magic.services.effect_handlers.summon_ally` gained an opt-in
  `payload.military` branch (`_summon_military_unit`, #1711) that creates a `BattleUnit` via
  `add_unit` in the caster's active `Battle` instead of a skirmish `CombatOpponent` — for
  summons too potent for a discrete-encounter skirmish.
- **Checks** — `perform_check`, sourced from the cast technique's
  `action_template.check_type` (via `use_technique`), not a generic battle-wide `CheckType`;
  the Surrounded entry roll and per-round resist checks are dispatched through
  `world.checks.consequence_resolution.select_consequence` against authored
  `ConsequencePool` rows (#1733)
- **Combat** — `BattlePlace.combat_encounter` bridge seam, now wired for Champion duels
  (`open_champion_duel`, #1710); `RoundStatus` and `AbstractRound` shared from
  `world.scenes`
- **Covenants** — `BattleSide.covenant` FK; `CovenantRole.command_tier`/
  `.is_champion_role` gate SIDE/PLACE-scope declarations and Champion duels (#1710)
- **Stories** — `Battle.campaign_story` FK (informational; not used for beat
  resolution); `world.battles.beat_wiring` resolves linked `Beat`s via
  `Scene → EpisodeScene → Episode` (#1785)
- **Actions** — four REGISTRY actions, `BattleRoundContext` in `get_active_round_context`

## Source

`src/world/battles/`
- `models.py` — all battle models
- `constants.py` — enums + tuning constants
- `services.py` — all service functions (setup + declaration + conclusion)
- `resolution.py` — `resolve_battle_round` + `BattleRoundResult` + the #1711 modifier stack
- `round_context.py` — `BattleRoundContext` + `resolve_battle_round_context`
- `exceptions.py` — exception hierarchy
- `factories.py` — FactoryBoy factories for all models + `ensure_battle_command_modifier_target` (#1711)
- `admin.py` — Django admin registrations for every battle model (#1711)

`src/actions/definitions/battles.py` — four REGISTRY actions

`src/commands/battle.py` — `CmdBattle` telnet namespace
