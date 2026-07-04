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
| `movement_cost` | PositiveSmallIntegerField | Default 1 (#1711). Authored cost for a future reposition/movement action — not yet filed as an issue; #1712 explicitly did not build this. Data only. |
| `controlled_by` | FK → `BattleSide` (null, `related_name="controlled_places"`) | Which side holds this front as an objective (#1712); set by a successful HOLD declaration. `None` means uncontrolled/contested. |
| `weather_override` | FK → `WeatherType` (null, `related_name="overriding_battle_places"`) | Local weather exception at this front (#1715); beats the Battle-level ambient weather here only. Cleared at round-boundary expiry. |
| `weather_override_expires_round` | PositiveIntegerField (null) | Absolute round number `weather_override` expires at (#1715). Cleared alongside `weather_override` at round-boundary expiry. |
| `x` / `y` | DecimalField(8, 2) (default 0) | Position on the battle's internal battle-map coordinate plane (#1714). Additive to ADR-0081 — see ADR-0085. |
| `footprint_radius` | DecimalField(6, 2) (default 1) | How much of the battle-map grid this place occupies (#1714). Two places overlap when the distance between their `(x, y)` centers is less than the sum of their `footprint_radius` values — see `world.battles.services.places_overlap`. |

**Constraint:** unique `(battle, name)`.

### `Fortification`

A defensible structure (wall/gate/battlement) at a `BattlePlace` (#1713). A front may
carry multiple `Fortification` rows — an outer wall, a gate, and a battlement — each
independently breachable via its own `integrity`/`max_integrity` (see ADR-0083). See
[Sieges (#1713)](#sieges-1713) below for the BREACH/FORTIFY verbs that act on it.

| Field | Type | Notes |
|---|---|---|
| `place` | FK → `BattlePlace` (`related_name="fortifications"`) | The front this structure defends |
| `defending_side` | FK → `BattleSide` (`related_name="fortifications"`) | The side this structure protects; gates BREACH (must differ) vs FORTIFY (must match) |
| `building` | FK → `buildings.Building` (null, `related_name="battle_fortifications"`) | Optional persistent Building this structure's integrity ceiling derives from; `None` means an ad-hoc, non-persistent structure |
| `kind` | CharField | `FortificationKind` — WALL / GATE / BATTLEMENT; default WALL. Purely descriptive plus a base-integrity lookup — BREACH/FORTIFY behave identically regardless of kind in this MVP |
| `integrity` | PositiveSmallIntegerField | Default 0; attrited by BREACH, restored by FORTIFY (capped at `max_integrity`) |
| `max_integrity` | PositiveSmallIntegerField | Default 0; snapshotted once at creation from `BASE_INTEGRITY[kind]` plus `building.fortification_level × FORTIFICATION_LEVEL_INTEGRITY_BONUS` if `building` is set — see `world.battles.services.create_fortification` |
| `breached` | BooleanField | Default False; set True when `integrity` reaches 0 via BREACH. Terminal — a breached structure can no longer be targeted by BREACH or FORTIFY |

**Ordering:** `["place", "kind", "id"]`.

### `BattleUnit`

An abstract typed force (enemy or friendly) stationed at a front.

| Field | Type | Notes |
|---|---|---|
| `battle` | FK → `Battle` (`related_name="units"`) | |
| `side` | FK → `BattleSide` (`related_name="units"`) | |
| `place` | FK → `BattlePlace` (null) | Optional front assignment |
| `name` | CharField(120) | Display name (e.g. "Cavalry") |
| `descriptor` | CharField(80), blank | Optional flavor tag (e.g. "zombies-on-nightmares"); narrative only — `properties`/`capabilities`/`quality` below drive mechanics. Renamed from the spine's `unit_type` (#1711). |
| `properties` | M2M → `mechanics.Property` (blank, `related_name="battle_units"`) | Descriptive tags this unit carries (flying, aquatic, metal-clad, etc.) — the same catalog characters use (#1794). Presence-only, no per-unit magnitude. Drives type-matchup and terrain-effect lookups (summed across every matching row, replacing #1711's single-select `composition`). |
| `capabilities` | M2M → `conditions.CapabilityType` through `BattleUnitCapability` (blank, `related_name="battle_units"`) | What this unit can DO, at an authored per-unit magnitude (#1794) — e.g. two units can both hold FLYING at very different values. |
| `individual_count` | PositiveIntegerField (null) | Population data point mirroring `CombatOpponent.swarm_count`'s naming/shape (#1794); `None` means "not a swarm-style unit". Data only — no swarm-math resolution wired against it yet. |
| `quality` | CharField | `UnitQuality` — MILITIA / LEVY / TRAINED / VETERAN / ELITE (#1711); default TRAINED. Flat attacker-facing STRIKE-check modifier ladder, not a strength multiplier. |
| `commander` | FK → `character_sheets.CharacterSheet` (null, `related_name="commanded_battle_units"`) | Optional commander (#1711); their Battle Command modifier-walk bonus applies to participants fighting alongside this unit's side/place. |
| `summoned_by` | FK → `character_sheets.CharacterSheet` (null, `related_name="summoned_battle_units"`) | Set when this unit was created via a military-grade summon (#1711, see `_summon_military_unit`). |
| `strength` | PositiveSmallIntegerField | Default 100; decremented by STRIKE successes |
| `morale` | PositiveSmallIntegerField | Default `DEFAULT_MORALE` (70, #1712); second resource alongside strength — starts well below its ceiling, unlike strength. |
| `status` | CharField | `BattleUnitStatus` — ACTIVE / ROUTED / DESTROYED; always a derived view, never written independently (see below) |

`status` is derived jointly from `strength` and `morale` by
`world.battles.resolution._compute_unit_status` (#1712) — every unit-status write
(STRIKE resolution, champion-duel-outcome routs) goes through this shared function
rather than writing `status` directly. DESTROYED requires `strength == 0` (physical
destruction; morale collapse alone never kills a unit). ROUTED is triggered by
either resource crossing its own threshold: `strength ≤ 30` (`ROUTED_STRENGTH_THRESHOLD`)
or `morale ≤ 25` (`ROUTED_MORALE_THRESHOLD`). Strength is decremented by
`success_level × STRIKE_ATTRITION_PER_LEVEL` (10 per level).

**Property/Capability holding (#1794):** `BattleUnit.effective_capability(capability)`
returns the authored magnitude from its own `BattleUnitCapability` rows (0 if absent),
and `BattleUnit.has_property(prop)` checks its `properties` M2M — both conform to
`world.mechanics.types.HasCapabilities`/`HasProperties`, the same `typing.Protocol`s
`CharacterSheet.effective_capability`/`has_property` implement. No `isinstance`
branching is needed anywhere a holder is read generically (e.g. the modifier stack
below).

### `BattleUnitCapability`

Authored `(unit, capability) → magnitude` row (#1794) — the through model for
`BattleUnit.capabilities`. Mirrors `mechanics.ObjectProperty`'s shape (one FK swapped:
`BattleUnit` for `ObjectDB`, `CapabilityType` for `Property`). No source-tracking FKs —
BattleUnit capabilities are static authored data, not subject to reactive
conditions/challenges.

| Field | Type | Notes |
|---|---|---|
| `unit` | FK → `BattleUnit` (`related_name="capability_values"`) | |
| `capability` | FK → `conditions.CapabilityType` (PROTECT, `related_name="battle_unit_values"`) | |
| `value` | PositiveIntegerField | Authored magnitude |

**Constraint:** unique `(unit, capability)`.

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
| `action_kind` | CharField | `BattleActionKind` — STRIKE / SUPPORT / RESCUE (#1733) / ROUT / RALLY / REPEL / HOLD (#1712) / BREACH / FORTIFY (#1713) |
| `target_unit` | FK → `BattleUnit` (null) | Strike target |
| `target_ally` | FK → `BattleParticipant` (null, `related_name="support_declarations"`) | Support target, or the Surrounded ally being rescued (RESCUE, #1733) |
| `target_fortification` | FK → `Fortification` (null) | Set when `action_kind` is BREACH or FORTIFY (#1713) |
| `resolved` | BooleanField | False until the GM resolves the round |
| `success_level` | SmallIntegerField | Check success level; >0 = success, ≤0 = failure |

**Constraint:** unique `(battle_round, participant)` — one declaration per participant
per round. Participants may redeclare (the service uses `update_or_create`).

### `TechniquePropertyAffinity`

Authored `(technique, property) → flat STRIKE-check modifier` row (#1794, replacing
#1711's `TechniqueCompositionAffinity`). Positive means the technique is especially
effective against that property; negative means weak against it. Summed across every
one of a unit's `properties` that has a matching row — a unit can carry several
properties at once, unlike the old single-select `composition`.

| Field | Type | Notes |
|---|---|---|
| `technique` | FK → `magic.Technique` (PROTECT, `related_name="battle_property_affinities"`) | |
| `property` | FK → `mechanics.Property` (PROTECT, `related_name="battle_technique_affinities"`) | |
| `modifier` | SmallIntegerField | Signed flat check modifier |

**Constraint:** unique `(technique, property)`.

Looked up by `_property_affinity_modifier(technique, holder)` (`world.battles.resolution`)
— sums every row matching one of `holder.has_property(...)`'s properties; returns 0 (no
effect) when none match — most techniques have no authored affinity. `holder` conforms
to `world.mechanics.types.HasProperties`.

### `TerrainPropertyEffect`

Authored `(terrain_type, property) → flat attacker-facing STRIKE modifier` row (#1794,
replacing #1711's `TerrainCompositionEffect`). Positive means a unit with that property
is easier to strike in that terrain; negative means harder. Summed across every one of
a unit's `properties` that has a matching row.

| Field | Type | Notes |
|---|---|---|
| `terrain_type` | CharField | `TerrainType` value |
| `property` | FK → `mechanics.Property` (PROTECT, `related_name="battle_terrain_effects"`) | |
| `modifier` | SmallIntegerField | Signed flat check modifier |

**Constraint:** unique `(terrain_type, property)`.

Looked up by `_terrain_property_modifier(place, holder)` (`world.battles.resolution`)
against the target unit's `place.terrain_type`, summed across matching properties;
returns 0 when the unit has no place, or no row matches.

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
   - ROUT: damages the target unit(s)' `morale` by `success_level × ROUT_MORALE_PER_LEVEL`
     (excludes the caster's own side); awards `success_level × ROUT_VP_PER_LEVEL` VP.
   - RALLY: restores the target unit(s)' `morale` by `success_level ×
     RALLY_MORALE_PER_LEVEL` (own side only, reaches ROUTED units too); awards flat
     `RALLY_VP`.
   - REPEL: raises a same-round defense bonus at the target place (`REPEL_DEFENSE_BONUS`,
     resolved before STRIKE within the round) reducing enemy STRIKE attrition there;
     awards flat `REPEL_VP`. Requires `scope=PLACE`.
   - HOLD: captures or sustains control of the target place (`BattlePlace.controlled_by`);
     awards `HOLD_CAPTURE_VP` on capture, `HOLD_SUSTAIN_VP` on sustain. Requires
     `scope=PLACE`.
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
| Property affinity | `_property_affinity_modifier(technique, unit)` | Sums every `TechniquePropertyAffinity` row matching one of `unit`'s `properties` (#1794); 0 if none match |
| Terrain effect | `_terrain_property_modifier(unit.place, unit)` | Sums every `TerrainPropertyEffect` row matching one of `unit`'s `properties` for `unit.place.terrain_type` (#1794); 0 if the unit has no place or no row matches |
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

## Battle-flow actions: Rout, Rally, Repel, Hold (#1712)

Four more `BattleActionKind` values round out the round economy beyond STRIKE/SUPPORT/
RESCUE. ROUT damages an enemy unit's `morale` the same way STRIKE damages `strength`
(`success_level × ROUT_MORALE_PER_LEVEL`, own-side excluded, flat VP-per-level); RALLY is
its mirror on the declarant's own side, restoring `morale` (including already-ROUTED
units — reaching broken units back to fighting shape is the whole point) and awarding a
flat `RALLY_VP`. REPEL and HOLD are PLACE-scope only (`PlaceScopeRequiredError` if declared
with any other scope): REPEL raises a same-round defense bonus at the target front
(`REPEL_DEFENSE_BONUS`) that reduces STRIKE attrition against units there, and — because
the bonus must exist before STRIKE reads it — `resolve_battle_round` resolves every REPEL
declaration first, ahead of every other action kind, with a stable sort preserving relative
order otherwise. HOLD captures or sustains a front's `BattlePlace.controlled_by`: capturing
an uncontrolled or enemy-held place awards the larger `HOLD_CAPTURE_VP` and flips control;
sustaining a place the declarant's side already holds awards the smaller `HOLD_SUSTAIN_VP`
with no state change, so repeatedly holding a front doesn't runaway-farm the capture bonus.

All four kinds route their unit-status writes through the same
`world.battles.resolution._compute_unit_status(strength, morale)` derivation STRIKE and the
Champion-duel outcome already use (see the `BattleUnit` table above) — no action kind ever
writes `status` directly, so ROUT dropping morale to zero and STRIKE dropping strength to
30 can both independently flip a unit to ROUTED without either handler needing to know
about the other's resource.

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
| `add_unit` | `(*, battle, side, name, descriptor="", quality=UnitQuality.TRAINED, commander=None, summoned_by=None, strength=100, place=None, properties=(), capability_values=(), individual_count=None) -> BattleUnit` | Adds an abstract unit (#1711: `descriptor` replaces `unit_type`; adds `quality`/`commander`/`summoned_by`. #1794: `properties` — iterable of `Property` to attach; `capability_values` — iterable of `(CapabilityType, magnitude)` pairs, each becomes a `BattleUnitCapability` row; `individual_count` — optional population data point) |
| `create_fortification` | `(*, place, defending_side, kind=FortificationKind.WALL, building=None) -> Fortification` | Creates a `Fortification` at `place`, snapshotting `max_integrity` once from `BASE_INTEGRITY[kind]` plus `building.fortification_level × FORTIFICATION_LEVEL_INTEGRITY_BONUS` if `building` is given (#1713) |
| `set_battle_side_posture` | `(*, side, posture) -> BattleSide` | Sets a side's `BattlePosture` (#1711) |
| `assign_unit_commander` | `(*, unit, commander) -> BattleUnit` | Assigns (or clears, with `commander=None`) a unit's commander (#1711) |
| `enlist_participant` | `(*, battle, character_sheet, side, place=None) -> BattleParticipant` | Enlists a PC |
| `begin_battle_round` | `(*, battle) -> BattleRound` | Closes prior round (→ COMPLETED) and opens a new DECLARING round. Raises `BattleConcludedError` if already concluded. |
| `declare_battle_action` | `(*, participant, action_kind, technique, target_unit=None, target_ally=None, scope=BattleActionScope.UNIT, target_place=None, target_side=None, target_fortification=None) -> BattleActionDeclaration` | Records or updates the participant's action declaration for the current DECLARING round. `scope`/`target_place`/`target_side` gate army/unit-scale declarations against command tier (#1710); `target_fortification` gates BREACH/FORTIFY ownership (#1713). Raises `RoundNotOpenError` if no DECLARING round, `CharacterDoesNotKnowTechniqueError` if the character doesn't know `technique`, `TechniqueNotBattleReadyError` if `technique` has no `action_template`, `NoCommandHierarchyError`/`InsufficientCommandTierError`/`MissingScopeTargetError`/`CannotStrikeOwnSideError` for scope violations, `FortificationTargetRequiredError`/`FortificationAlreadyBreachedError`/`FortificationOwnershipMismatchError` for BREACH/FORTIFY violations. |
| `open_champion_duel` | `(*, battle_place, challenger_participant, opponent_kwargs, tier=OpponentTier.BOSS) -> CombatEncounter` | Binds `battle_place` to a new lethal duel (reuses `create_lethal_duel` unmodified) if the challenger holds an engaged Champion role (#1710). Raises `NotAChampionError`/`NoCommandHierarchyError`/`PlaceAlreadyDuelingError`. |
| `open_siege_engine_encounter` | `(*, battle_place, participant, opponent_kwargs, tier=OpponentTier.ELITE) -> CombatEncounter` | Binds `battle_place` to a discrete siege-engine skirmish — same bridge and `create_lethal_duel` call as `open_champion_duel`, no Champion-role requirement (#1713). Raises `PlaceAlreadyDuelingError`. |
| `check_victory` | `(*, battle) -> BattleOutcome \| None` | Returns the graded outcome if any side has reached its threshold, else None. Decisive if margin ≥ `DECISIVE_MARGIN` (50). |
| `conclude_battle` | `(*, battle, outcome) -> Battle` | Sets outcome + `concluded_at`; ends the backing scene (`is_active=False`); resolves any linked story beat's stakes contract via `resolve_battle_beats` (#1785). Does NOT call `complete_story` — a war arc spans multiple battles, so one battle's conclusion must not auto-close the whole campaign story. Idempotent. |
| `maybe_conclude_on_timer` | `(*, battle) -> BattleOutcome \| None` | Fires when no active round exists and `completed_round_count >= round_limit`. Timeout rule: defender holds unless attacker meets threshold. |
| `create_battle_vehicle` | `(*, battle, side, place_name, vehicle_kind=VehicleKind.SHIP, is_structural=True) -> BattleVehicle` | Creates a vessel/mount: a paired `BattleUnit` + `BattlePlace`, plus a hull `Fortification` if `is_structural` (#1714). The unit's own `place` stays `None`; other units/participants embed by pointing their own `place` FK at `vehicle.place`. |
| `places_overlap` | `(place_a, place_b) -> bool` | Whether two `BattlePlace` footprints intersect on the battle map: distance between `(x, y)` centers < sum of `footprint_radius` values (#1714, ADR-0085). |

## Actions (`src/actions/definitions/battles.py`)

Four REGISTRY actions, all registered in `src/actions/registry.py`:

| Key | Class | target_type | Who | Effect |
|---|---|---|---|---|
| `begin_battle_round` | `BeginBattleRoundAction` | AREA | GM / staff | Opens a new DECLARING round |
| `resolve_battle_round` | `ResolveBattleRoundAction` | AREA | GM / staff | Resolves current round; auto-concludes if `check_victory` fires |
| `conclude_battle` | `ConcludeBattleAction` | AREA | GM / staff | Force-concludes; tries natural win → timer → DEFENDER_MARGINAL default |
| `declare_battle_action` | `DeclareBattleActionAction` | SELF | Player | Records a declaration (`technique_id` plus `action_kind`/`target_unit`/`target_ally`/`scope`/`target_place`/`target_side`/`target_fortification` kwargs) for the current round. All 9 `BattleActionKind` values, including BREACH/FORTIFY, are reachable through this Action and the `battle declare breach\|fortify` telnet grammar (#1713). |

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
| `battle declare rout <unit> with <technique>` | Declare ROUT against an ACTIVE enemy unit, damaging its `morale` (#1712) |
| `battle declare rally <unit> with <technique>` | Declare RALLY on a unit on your own side (ACTIVE or ROUTED), restoring its `morale` (#1712) |
| `battle declare repel place <name> with <technique>` | Declare REPEL at a front (PLACE-scope only), raising a same-round defense bonus there (#1712) |
| `battle declare hold place <name> with <technique>` | Declare HOLD at a front (PLACE-scope only), capturing or sustaining `BattlePlace.controlled_by` (#1712) |
| `battle duel <front> vs <boss name>` | Challenge a lethal Champion duel bound to a front (requires an engaged Champion role, #1710) |
| `battle round` | GM: begin the next round |
| `battle resolve` | GM: resolve the current round |
| `battle conclude` | GM: force-conclude the battle |

`strike`/`rout`/`rally` also accept `side` or `place <name>` in place of a unit name
(SIDE-scope requires an engaged SUPREME command tier; PLACE-scope requires engaged
SUBORDINATE/SUPREME — see [Command Hierarchy & the
Champion](#command-hierarchy--the-champion-1710) below). `strike`/`rout` target the
opposing side by default; `rally`'s `side`/`place <name>` target the declarant's own side
instead (rallying the enemy makes no sense). Unit names are resolved case-insensitively
within the caller's active battle — STRIKE/ROUT match any side's ACTIVE units
(`_resolve_unit`); RALLY matches only the declarant's own side, ACTIVE or ROUTED
(`_resolve_own_unit`, #1712). Ally names are resolved by `character.db_key`
case-insensitively. Technique names are resolved case-insensitively against the caller's
known `CharacterTechnique` rows (`_resolve_technique`); an unknown name raises
`CommandError`. `CommandError` is raised for bad usage; `_send(result)` routes the
`ActionResult.message` back to the caller.

## Admin (`src/world/battles/admin.py`)

New file (#1711) — the shipped spine (#1592) had zero admin exposure. Registers every
battle model with a `ModelAdmin`: `Battle`, `BattleSide` (list-filtered on `role`/`posture`),
`BattlePlace` (list-filtered on `terrain_type`; `controlled_by` shown in `list_display` and
as an autocomplete field, #1712), `BattleUnit` (`morale` shown alongside `strength` in
`list_display`, #1712; list-filtered on `quality`/`status`; `commander`/`summoned_by` as
autocomplete fields; `properties` via `filter_horizontal` and a `BattleUnitCapabilityInline`
tabular inline for `BattleUnitCapability` rows, #1794), `BattleRound`, `BattleParticipant`,
`BattleActionDeclaration`, and the two authored catalogs `TechniquePropertyAffinity`
(list-filtered on `property`; `technique`/`property` as autocomplete fields, #1794) and
`TerrainPropertyEffect` (list-filtered on `terrain_type`/`property`; `property` as an
autocomplete field, #1794), giving staff a CRUD surface to author the type-matchup and
terrain-effect content the modifier stack reads, and `Fortification` (#1713;
list-filtered on `kind`/`breached`; `place`/`defending_side`/`integrity`/`max_integrity`/
`breached` in `list_display`).

## Enums / Constants (`src/world/battles/constants.py`)

| Name | Kind | Values |
|---|---|---|
| `BattleSideRole` | TextChoices | ATTACKER / DEFENDER |
| `BattleUnitStatus` | TextChoices | ACTIVE / ROUTED / DESTROYED |
| `BattleParticipantStatus` | TextChoices | ACTIVE / WITHDRAWN / INCAPACITATED |
| `BattleActionKind` | TextChoices | STRIKE / SUPPORT / RESCUE (#1733) / ROUT / RALLY / REPEL / HOLD (#1712) / BREACH / FORTIFY (#1713) |
| `BattleOutcome` | TextChoices | UNRESOLVED / ATTACKER_DECISIVE / ATTACKER_MARGINAL / DEFENDER_MARGINAL / DEFENDER_DECISIVE |
| `UnitQuality` | TextChoices | MILITIA / LEVY / TRAINED / VETERAN / ELITE (#1711) |
| `TerrainType` | TextChoices | OPEN / DIFFICULT / FORTIFIED / ELEVATED / FLOODED / URBAN (#1711) |
| `BattlePosture` | TextChoices | BALANCED / AGGRESSIVE / DEFENSIVE (#1711) |
| `FortificationKind` | TextChoices | WALL / GATE / BATTLEMENT (#1713) |

**Tuning constants:**
- `DEFAULT_VICTORY_THRESHOLD = 100`
- `DEFAULT_ROUND_LIMIT = 10`
- `STRIKE_ATTRITION_PER_LEVEL = 10`
- `STRIKE_VP_PER_LEVEL = 5`
- `SUPPORT_VP = 3`
- `BASE_FAILURE_DAMAGE = 8`
- `DECISIVE_MARGIN = 50`
- `ROUTED_STRENGTH_THRESHOLD = 30`
- `DEFAULT_MORALE = 70` — `BattleUnit.morale` starting value (#1712); unlike strength, morale starts well below its ceiling
- `MAX_MORALE = 100`
- `ROUTED_MORALE_THRESHOLD = 25` — the morale-axis counterpart to `ROUTED_STRENGTH_THRESHOLD` in `_compute_unit_status`
- `SURROUNDED_ENTRY_ISOLATED_MODIFIER = -15` — entry-roll signal (#1733), isolated at a place
- `SURROUNDED_ENTRY_MOBILITY_MODIFIER = 40` — entry-roll signal (#1733), unimpaired MOVEMENT capability
- `UNIT_QUALITY_STRIKE_MODIFIER` — dict (#1711), flat attacker-facing STRIKE modifier per `UnitQuality`: MILITIA +10 … ELITE −20
- `BATTLE_POSTURE_VP_MULTIPLIER` — dict (#1711), percent VP-gain scaling per `BattlePosture`: AGGRESSIVE 1.4, BALANCED 1.0, DEFENSIVE 0.7
- `BATTLE_POSTURE_CHECK_MODIFIER` — dict (#1711), flat STRIKE-check modifier per `BattlePosture`: AGGRESSIVE −5, BALANCED 0, DEFENSIVE +10
- `BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER` — dict (#1711), flat failure-damage modifier per `BattlePosture`: AGGRESSIVE +4, BALANCED 0, DEFENSIVE −4
- `BATTLE_COMMAND_TARGET_NAME = "battle_command"` — idempotent-seed `ModifierTarget` name (#1711)
  for the commander-bonus walk, following the snake_case convention documented for
  stat-category modifier targets in `world/mechanics/CLAUDE.md`.
- `ROUT_MORALE_PER_LEVEL = 15` — ROUT's morale damage per success level (#1712), mirrors
  `STRIKE_ATTRITION_PER_LEVEL`'s scaling
- `RALLY_MORALE_PER_LEVEL = 15` — RALLY's morale restoration per success level (#1712)
- `ROUT_VP_PER_LEVEL = 4` — ROUT's VP award per success level (#1712)
- `RALLY_VP = 3` — RALLY's flat VP award (#1712)
- `REPEL_VP = 4` — REPEL's flat VP award (#1712)
- `HOLD_CAPTURE_VP = 8` — HOLD's VP award for capturing an uncontrolled/enemy-held place (#1712)
- `HOLD_SUSTAIN_VP = 3` — HOLD's smaller VP award for sustaining a place the side already
  controls (#1712) — deliberately less than capture so holding a front doesn't runaway-farm VP
- `REPEL_DEFENSE_BONUS = 15` — flat reduction applied to STRIKE attrition against units at a
  place with a REPEL declared this round (#1712)
- `BASE_INTEGRITY` — dict (#1713), starting `Fortification.max_integrity` ceiling per
  `FortificationKind` before any persistent investment: WALL 100, BATTLEMENT 80, GATE 60
- `FORTIFICATION_LEVEL_INTEGRITY_BONUS = 20` — flat per-level ladder bonus (#1713) applied per
  `Building.fortification_level` when a `Fortification` is created against a persistent `building`
- `BREACH_INTEGRITY_PER_LEVEL = 10` — BREACH's integrity damage per success level (#1713), mirrors
  `STRIKE_ATTRITION_PER_LEVEL`'s scaling
- `FORTIFY_INTEGRITY_PER_LEVEL = 15` — FORTIFY's integrity restoration per success level (#1713),
  mirrors `RALLY_MORALE_PER_LEVEL`'s scaling
- `BREACH_VP_PER_LEVEL = 5` — BREACH's VP award per success level (#1713)
- `FORTIFY_VP = 3` — FORTIFY's flat VP award (#1713)

## Exceptions (`src/world/battles/exceptions.py`)

- `BattleError(Exception)` — base; carries `user_message`
  - `BattleConcludedError` — operation on already-concluded battle
  - `RoundNotOpenError` — declaration outside a DECLARING round
  - `NotAParticipantError` — character not enlisted in the battle
  - `CharacterDoesNotKnowTechniqueError` — participant declared a technique they don't know
  - `TechniqueNotBattleReadyError` — declared technique has no `action_template` (not castable)
  - `NoCommandHierarchyError` — PLACE/SIDE-scope declaration (or Champion duel) on a side
    with no covenant (#1710)
  - `InsufficientCommandTierError` — participant lacks the engaged command tier their
    declared scope requires (#1710)
  - `MissingScopeTargetError` — PLACE scope with no `target_place`, or SIDE scope with no
    `target_side` (#1710)
  - `CannotStrikeOwnSideError` — STRIKE or ROUT, scope=SIDE, `target_side` is the caster's
    own side (#1710; extended to ROUT in #1712's final review)
  - `NotAChampionError` — challenger holds no engaged `is_champion_role` `CovenantRole`
    (#1710)
  - `PlaceAlreadyDuelingError` — `BattlePlace.combat_encounter` is already set (#1710;
    also raised by `open_siege_engine_encounter`, #1713)
  - `PlaceScopeRequiredError` — REPEL/HOLD declared with a scope other than PLACE (#1712)
  - `FortificationTargetRequiredError` — BREACH/FORTIFY declared with no
    `target_fortification` (#1713)
  - `FortificationOwnershipMismatchError` — BREACH targets your own side's
    `Fortification`, or FORTIFY targets the enemy's (#1713)
  - `FortificationAlreadyBreachedError` — BREACH/FORTIFY targets a `Fortification`
    with `breached=True` (#1713)

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
quality/commander taxonomy (`BattleUnit.quality`/`.commander`/`.summoned_by`, replacing
`unit_type` with the narrative-only `descriptor`); front terrain
(`BattlePlace.terrain_type`/`.movement_cost`); side tactical posture
(`BattleSide.posture`); authored type-matchup/terrain-effect catalogs; the five-source
[modifier stack](#modifier-stack-1711) folded into every STRIKE check; Django admin for
the whole app (`admin.py`, previously absent); and an opt-in
`summon_ally(payload.military=True)` branch that creates a `BattleUnit` instead of a
skirmish `CombatOpponent` (see [Integrates With](#integrates-with) below).

**Built as a follow-up spine (Property/Capability holding, #1794):** #1711's single-select
`BattleUnit.composition` (`UnitComposition` enum) was replaced with `properties` (plain
M2M → `mechanics.Property`, presence-only tags) and `capabilities` (M2M →
`conditions.CapabilityType` through `BattleUnitCapability`, an authored per-unit
magnitude) — a unit can now carry several properties/capabilities at once instead of one
composition tag, and two units can hold the same capability at different values.
`individual_count` (nullable, data-only) mirrors `CombatOpponent.swarm_count`'s naming.
`TechniqueCompositionAffinity`/`TerrainCompositionEffect` were replaced by
`TechniquePropertyAffinity`/`TerrainPropertyEffect`, both keyed on `Property` and summed
across every matching property a unit carries. Two new `typing.Protocol`s,
`HasProperties`/`HasCapabilities` (`world.mechanics.types`), let the modifier stack and
`CharacterSheet` share the same duck-typed interface with no `isinstance` branching.

**Built as a follow-up spine (battle-flow actions, #1712):** `BattleUnit.morale`, a second
numeric resource alongside `strength` (default `DEFAULT_MORALE`, 70 — unlike strength,
morale starts well below its ceiling); `status` is now always derived jointly from both via
`_compute_unit_status` rather than from `strength` alone. Four new `BattleActionKind`
values — ROUT/RALLY (unit-scale, move the morale axis) and REPEL/HOLD (PLACE-scope only,
round-level defense bonus / front-control objective) — see
[Battle-flow actions](#battle-flow-actions-rout-rally-repel-hold-1712) above.
`BattlePlace.controlled_by` (nullable FK → `BattleSide`), set by a successful HOLD
declaration. Telnet grammar for all four (`battle declare rout/rally/repel/hold ...`).

**Deferred to follow-up issues:**

| What | Issue |
|---|---|
| Battle writeup / React page | #1735 |
| Naval / aerial variants | #1714 (deferred) |
| Siege variants | **built, see [Sieges (#1713)](#sieges-1713) below** |

Peril / rescue and the AFK knob are no longer deferred — see
[Peril / Rescue (#1733)](#peril--rescue-1733) below. Rich unit type-matchups and terrain
effects are no longer deferred — see [Modifier Stack (#1711)](#modifier-stack-1711) above.
Campaign propagation (battle outcome → Story + win-gated Legend) is no longer deferred — see
[Stakes / Beat Wiring (#1785)](#stakes--beat-wiring-1785) below. Command hierarchy and the
Champion are no longer deferred — see
[Command Hierarchy & the Champion (#1710)](#command-hierarchy--the-champion-1710) below.
Siege variants are no longer deferred — see [Sieges (#1713)](#sieges-1713) below.

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
the side's covenant. `world.battles.resolution._resolve_strike_success`,
`_resolve_rescue_success`, `_resolve_rout_success`, and `_resolve_rally_success` (#1712)
all fan out across every active unit/participant at the scope target instead of a
single one.

The Champion duel reuses `world.combat.duels.create_lethal_duel` unmodified —
`world.battles.services.open_champion_duel` validates the challenger holds an engaged
`is_champion_role` `CovenantRole`, then binds the resulting `CombatEncounter` to the
`BattlePlace.combat_encounter` bridge seam (the first real caller of that seam since
#1592). Outcome feedback (rout/destroy the losing side's unit at that front, VP bonus
to the winner) is wired via `world.battles.duel_wiring`, mirroring
`world.combat.beat_wiring`'s `ENCOUNTER_COMPLETED` `TriggerDefinition` pattern exactly
— no new event type.

## Sieges (#1713)

Siege warfare is a battle variety built on two new pieces: the `Fortification`
model (a defensible structure at a front — see [`Fortification`](#fortification)
above) and the `BREACH`/`FORTIFY` `BattleActionKind` pair that acts on it. A
`BattlePlace` may carry several `Fortification` rows at once (an outer wall, a
gate, a battlement), each independently ground down or shored up — see
**ADR-0083** for why this is per-structure state rather than a single shared
value on `BattlePlace` itself, and why BREACH/FORTIFY are a dedicated verb pair
rather than a reuse of STRIKE/REPEL.

**BREACH** (attacker verb) and **FORTIFY** (defender verb) both declare against a
`target_fortification`, validated in `declare_battle_action`
(`world.battles.services._validate_fortification_target`): the target must be set
(`FortificationTargetRequiredError` if not), must not already be `breached`
(`FortificationAlreadyBreachedError`), and its `defending_side` must differ from
the declaring participant's side for BREACH or match it for FORTIFY
(`FortificationOwnershipMismatchError` otherwise — a side may only tear down the
enemy's structures or shore up its own). Resolution
(`world.battles.resolution._resolve_breach_success` /
`_resolve_fortify_success`) mirrors the existing resource-verb pairs: BREACH
attrites `integrity` by `success_level × BREACH_INTEGRITY_PER_LEVEL` (setting
`breached = True` once it reaches 0 — terminal, matching STRIKE's attrition of
`BattleUnit.strength`) and awards `success_level × BREACH_VP_PER_LEVEL` VP;
FORTIFY restores `integrity` by `success_level × FORTIFY_INTEGRITY_PER_LEVEL`
(capped at `max_integrity`, matching RALLY's restoration of `morale`) and awards a
flat `FORTIFY_VP`. Both scale VP with `BATTLE_POSTURE_VP_MULTIPLIER` like every
other VP-awarding kind.

`open_siege_engine_encounter` (`world.battles.services`) binds a `BattlePlace` to a
discrete siege-engine skirmish the same way `open_champion_duel` (#1710) binds a
Champion challenge — reusing the `BattlePlace.combat_encounter` bridge and
`create_lethal_duel` — but without the Champion-role requirement, since sabotaging
a ram's crew or defending a tower is an ordinary discrete fight, not a duel gated
on covenant rank. Siege engines themselves are ordinary `BattleUnit` rows, not a
separate model — content authors differentiate one via the #1794 `properties`/
`capabilities` taxonomy (e.g. a descriptive `Property` tag) the same way any other
unit distinction is now authored, rather than a dedicated composition/kind field.
This function only opens the discrete-combat bridge for a skirmish over one.

A `Fortification`'s starting `max_integrity` can draw on a persistent, player-built
investment: `world.buildings.Building.fortification_level` (raised by a
`FORTIFICATION_UPGRADE` Project — see `world.buildings.fortification_services`,
`start_fortification_upgrade` / `complete_fortification_upgrade`, monotonic
max-set on completion so a lower-target Project completing after a higher one
never regresses the level). `create_fortification` snapshots this once, at
creation, into `max_integrity = BASE_INTEGRITY[kind] + building.fortification_level
× FORTIFICATION_LEVEL_INTEGRITY_BONUS` when a `building` is supplied — the same
snapshot-once-at-creation pattern `Building` itself uses for `target_size`/
`target_grandeur`. A `Fortification` created with `building=None` is an ad-hoc
structure with no persistent investment behind it (`max_integrity` is just
`BASE_INTEGRITY[kind]`).

BREACH/FORTIFY are fully wired end to end: `DeclareBattleActionAction` forwards a
`target_fortification` kwarg alongside the existing `action_kind`/`target_unit`/
`target_ally`/`scope`/`target_place`/`target_side` kwargs, and `CmdBattle` exposes
`battle declare breach place <name> fortification <kind> with <technique>` /
`battle declare fortify place <name> fortification <kind> with <technique>` —
the same `place <name>` disambiguator REPEL/HOLD use, plus a `fortification <kind>`
token since a front may carry more than one structure and a `Fortification` has no
name of its own (#1713). `open_siege_engine_encounter` remains the one exception:
it has no `ChallengeChampionDuelAction`-style Action or telnet counterpart yet.

## Test Coverage

- `src/world/battles/tests/test_constants.py` — enum smoke tests
- `src/world/battles/tests/test_models.py` — model save + side/unit relationships;
  `BattleUnitTaxonomyTests` (quality/commander/summoned_by/descriptor, #1711),
  `BattleUnitPropertyCapabilityTests` (`has_property`/`effective_capability`, including
  two units holding the same capability at distinct authored magnitudes, #1794),
  `TechniquePropertyAffinityTests`, `TerrainPropertyEffectTests` (#1794),
  `BattleUnitMoraleTests` (`morale` defaults to `DEFAULT_MORALE`, overridable),
  `BattlePlaceControlTests` (`controlled_by` defaults to `None`, `SET_NULL` on side
  delete) (#1712)
- `src/world/battles/tests/test_round_context.py` — `get_active_round_context` wiring
- `src/world/battles/tests/test_services_setup.py` — create/enlist/begin-round lifecycle;
  `AddUnitTests`, `AddUnitTaxonomyTests` (`add_unit`'s taxonomy kwargs, #1711; the
  `test_add_unit_accepts_properties_and_capability_values` case covers `add_unit`'s
  `properties`/`capability_values`/`individual_count` kwargs, #1794),
  `AddPlaceTerrainTests` (`add_place`'s `terrain_type`/`movement_cost` kwargs, #1711),
  `SetBattleSidePostureTests`, `AssignUnitCommanderTests` (#1711)
- `src/world/battles/tests/test_factories_seed.py` — `EnsureBattleCommandModifierTargetTests`
  (idempotent seeding of the `"battle_command"` `ModifierTarget`, #1711)
- `src/world/battles/tests/test_resolution.py` — `resolve_battle_technique` /
  `BattleTechniqueResolver` unit test; STRIKE success (unit attrition + VP) and failure
  (PC health debit) with `world.battles.resolution.perform_check` patched (the check inside
  `use_technique`'s cast, not a bypass of it); `PropertyAffinityModifierTests`,
  `TerrainPropertyModifierTests` (single-match and sums-across-multiple-properties cases,
  #1794), `QualityModifierTests`, `CommanderBonusForSideAtPlaceTests`,
  `BattleTechniqueResolverModifierStackTests` (the full five-source stack), and
  `PostureVpScalingTests` (VP-gain and failure-damage posture scaling) (#1711)
- `src/world/battles/tests/test_conclusion.py` — `check_victory` grading and
  `conclude_battle` (confirms `complete_story` is NOT called)
- `src/world/battles/tests/test_actions.py` — each action's `run()` path; GM-gate rejection
- `src/world/battles/tests/test_command.py` — telnet `battle declare strike <unit>` path,
  including `test_declare_rescue_dispatches_rescue_action_kind` (#1733);
  `test_declare_rout_creates_declaration`, `test_declare_rally_targets_own_routed_unit`,
  `test_declare_rally_rejects_enemy_side_unit_by_name`,
  `test_declare_repel_place_creates_declaration`,
  `test_declare_hold_without_place_scope_sends_usage` (#1712)
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
- `src/world/battles/tests/test_resolution.py` (#1712) — `ComputeUnitStatusTests`
  (`_compute_unit_status` DESTROYED-requires-zero-strength / ROUTED-from-either-axis
  matrix); `PlaceScopeRequiredError` raised for REPEL/HOLD declared outside PLACE scope
  (in `DeclareBattleActionTests`); `RoutResolutionTests` (morale damage, own-side
  exclusion, flip-to-ROUTED), `RallyResolutionTests` (morale restoration, MAX_MORALE
  clamp, own-side-only, cannot recover a unit ROUTED by low strength, PLACE-scope
  reaches ROUTED units), `RepelResolutionTests` (defense bonus reduces same-round STRIKE
  attrition at the target place), `HoldResolutionTests` (capture vs. sustain VP,
  capturing from enemy control, end-to-end capture via `resolve_battle_round`)
- `src/world/battles/tests/test_duel_wiring.py` (#1710) — Champion duel outcome
  auto-wiring: challenger victory routs the enemy unit at the bound place; a
  non-battle-bound encounter completion no-ops cleanly
- `src/world/battles/tests/test_siege.py` (#1713) — E2E siege journeys:
  `SiegeBreachJourneyTests` (BREACH against your own side's `Fortification` is
  rejected; repeated BREACH grinds `integrity` to 0, sets `breached`, and awards
  VP), `HoldTheWallsJourneyTests` (an untouched `Fortification` survives a
  no-declarations timeout — proves hold-the-walls needs zero siege-specific
  win-condition code, reusing `maybe_conclude_on_timer` unchanged),
  `FortificationInvestmentJourneyTests` (a funded `FORTIFICATION_UPGRADE`
  raises the snapshot integrity a subsequent `create_fortification` sees; a
  second, lower-target upgrade completing after a higher one never regresses it)
- `src/world/buildings/tests/test_fortification_upgrade_kind.py` (#1713) —
  `start_fortification_upgrade`/`complete_fortification_upgrade`: target-level
  validation (`FortificationLevelExceedsMaximumError`), monotonic max-set on
  completion, idempotent re-application via the `applied_at` claim

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
  Soulfray, Audere / Audere Majora escalation all apply); `TechniquePropertyAffinity.technique`
  FK (#1794). `world.magic.services.effect_handlers.summon_ally` gained an opt-in
  `payload.military` branch (`_summon_military_unit`, #1711) that creates a `BattleUnit` via
  `add_unit` in the caster's active `Battle` instead of a skirmish `CombatOpponent` — for
  summons too potent for a discrete-encounter skirmish. `payload.properties`
  (list[str] of `Property` names) / `payload.capabilities` (dict[str, int] of
  `CapabilityType` name → magnitude) are read and forwarded to `add_unit`'s
  `properties`/`capability_values` kwargs (#1794).
- **Mechanics** — `world.mechanics.types.HasProperties`/`HasCapabilities` `Protocol`s
  (#1794), implemented by both `BattleUnit` and `character_sheets.CharacterSheet` — the
  modifier stack's `_property_affinity_modifier`/`_terrain_property_modifier` read either
  kind of holder with no `isinstance` branching.
- **Checks** — `perform_check`, sourced from the cast technique's
  `action_template.check_type` (via `use_technique`), not a generic battle-wide `CheckType`;
  the Surrounded entry roll and per-round resist checks are dispatched through
  `world.checks.consequence_resolution.select_consequence` against authored
  `ConsequencePool` rows (#1733)
- **Combat** — `BattlePlace.combat_encounter` bridge seam, now wired for Champion duels
  (`open_champion_duel`, #1710) and siege-engine skirmishes (`open_siege_engine_encounter`,
  #1713); `RoundStatus` and `AbstractRound` shared from `world.scenes`
- **Buildings** — `Fortification.building` FK (optional; #1713) — a persistent
  `Building.fortification_level`, raised via a `FORTIFICATION_UPGRADE` Project
  (`world.buildings.fortification_services`), is snapshotted once into a new
  `Fortification`'s `max_integrity` by `create_fortification`
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
