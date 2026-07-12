# Battles glossary

**Battle**:
A large-scale multi-party engagement, a 1:1 extension of `scenes.Scene`. Owns
`BattleSide`s, `BattlePlace`s (fronts), abstract `BattleUnit`s, and per-round
`BattleActionDeclaration`s.
_Avoid_: encounter, fight (use `CombatEncounter` for a discrete tactical fight).

**Battle Side**:
One faction in a `Battle` (`ATTACKER`/`DEFENDER`) with its own victory-point tally.
Optionally fielded by a War Covenant (`BattleSide.covenant`, #1710) — a side with no
covenant has no command hierarchy. Carries a `BattlePosture` (balanced/aggressive/
defensive, #1711) trading VP-gain speed against check difficulty/failure damage.
_Avoid_: team, faction (use "side"); stance, tactics mode (use "posture").

**Battle Place**:
A named front/zone within a `Battle` (e.g. "The Main Gates"). Not a room; battles are
location-less (see ADR-0081). Carries a `TerrainType` (#1711) affecting
property/terrain-effect matchups (#1794). Can be bound to a real `CombatEncounter`
(`combat_encounter` FK) for a discrete tactical fight at that front — a Champion duel
(#1710), a siege-engine skirmish (#1713), or a general party encounter (#2008).
_Avoid_: front (descriptive only), zone, location.

**Weather Override**:
A cast-set (or, at the `Battle` level, ambient-seeded) `WeatherType` held on `Battle` or
`BattlePlace`, with a round-count expiry (#1715). See "Local Exception" for the
`BattlePlace`-level variant's precedence rule.
_Avoid_: environment state, weather condition (already means something else in
`world.conditions`).

**Local Exception**:
A `BattlePlace.weather_override` that beats the `Battle`-level `weather_override`/ambient
value at that front only (#1715) — cover, a ward, or a hostile local squall cast with
`BattleActionScope.PLACE`. Resolution order: local exception -> battle-wide override ->
ambient (via `Battle.region`) -> none. See `world.battles.resolution.effective_weather`.
_Avoid_: local override (ambiguous with the battle-wide tier), place weather.

**Weather Challenge**:
A `WeatherTypeCapabilityChallenge` row — an authored `(weather_type, capability, threshold,
modifier)` tuple applying when a unit's `effective_capability(capability)` falls strictly
below `threshold` (#1715). The first absence/threshold-based battle modifier in the
codebase; everything else is presence- (`has_property`) or `>=`-threshold
(`prerequisites_met`) based.
_Avoid_: capability penalty (too generic), weather vulnerability.

**Unit**:
A `BattleUnit` — an abstract typed force (friendly or enemy) stationed at a place.
Carries `properties` (a plain M2M to the same `Property` catalog characters use — see
`world/mechanics/AGENT_GLOSSARY.md`'s **Property** entry; presence-only tags like
flying/aquatic/metal-clad, #1794) driving type-matchups and terrain effects, and
`capabilities` (M2M to `CapabilityType` through `BattleUnitCapability`, an authored
per-unit magnitude — two units can hold the same capability at very different values,
#1794). Also carries a `UnitQuality` tier (militia through elite, #1711) — a flat
check-difficulty modifier ladder, not a strength multiplier — and an `individual_count`
(nullable population data point mirroring `CombatOpponent.swarm_count`, #1794; see
**Swarm-style unit** below for what it drives, #1841). Replaces the spine's
single-select `UnitComposition` enum (#1711), which could only ever tag a unit with
one composition.
_Avoid_: squad, regiment, mob; composition (superseded term — use properties/capabilities).

**Swarm-style unit**:
A `BattleUnit` with `individual_count` set (not `None`) — a horde/pack/flock counted
in bodies rather than resolved as a single formation. Drives two derived-math effects
(#1841): a banded flat STRIKE bonus (`swarm_strike_bonus`, `SWARM_STRIKE_BONUS_BANDS`
in `constants.py` — bigger swarm, easier to land a hit) folded into the same modifier
stack as terrain/weather/quality, and proportional body loss off `individual_count`
whenever the unit takes STRIKE attrition or ROUT morale damage (`_apply_swarm_losses`
in `resolution.py` — `ceil(individual_count * attrition / 100)`, since `strength`/
`morale` are both 0-100 scales). A unit with `individual_count=None` is never
swarm-style — neither effect applies, and it's excluded from
`BattleRoundResult.unit_losses`. Distinct from capital vessels (naval/aerial, #1714),
which stay on the separate per-hull `Fortification` integrity track rather than a
body count — see [ADR-0122](../../../docs/adr/0122-swarm-math-is-derived-losses-not-a-second-health-pool.md).
_Avoid_: swarm count (use `individual_count`, the actual field name); horde health
(this is not a second health pool — see the ADR).

**Morale**:
A `BattleUnit`'s second numeric resource (#1712), alongside `strength`. Unlike
strength (starts at its ceiling, only depletes), morale starts well below its
ceiling (`DEFAULT_MORALE`) and climbing it is comparatively hard — sitting near
`MAX_MORALE` reads as exceptional, not baseline. `status` is derived jointly
from both resources (`_compute_unit_status`) — never written independently. A
future unit property (Mindless, Fearless — see #1794, "Battle units:
Property/Capability holding") would exempt some units from the morale branch
of that derivation; no such mechanism exists yet.

**Rout** (verb):
The `BattleActionKind.ROUT` declaration — damages an enemy unit's `morale`
(#1712). Distinct from the `ROUTED` `BattleUnitStatus` value, which is a
*derived state* any sufficiently low `strength` or `morale` can trigger, not
something ROUT sets directly.

**Rally**:
The `BattleActionKind.RALLY` declaration — restores a friendly unit's `morale`
(#1712), including units already `ROUTED`. Cannot recover a unit whose
`ROUTED` status comes from low `strength` instead — RALLY only heals the
morale axis.

**Repel**:
The `BattleActionKind.REPEL` declaration (#1712, PLACE-scope only) — raises a
same-round defense bonus reducing enemy STRIKE attrition against units at that
front.

**Hold/Seize**:
The `BattleActionKind.HOLD` declaration (#1712, PLACE-scope only) — captures
or sustains control of a `BattlePlace` (see **Front control** below).

**Front control**:
`BattlePlace.controlled_by` (#1712) — which `BattleSide`, if any, currently
holds a front as an objective. `None` means uncontrolled/contested. Set by a
successful HOLD declaration.

**Move** (verb):
The `BattleActionKind.MOVE` declaration (#2007) — reassigns a `BattleParticipant`'s
or `BattleUnit`'s `.place` FK to a different, already-existing `BattlePlace`.
Distinct from **Reposition** below, which moves a `BattlePlace`'s own coordinates.
Self-move (`scope=UNIT`) needs no command authority; a commander orders one unit
(`scope=PLACE`) through the same Command Tier gate ROUT/RALLY use.
`target_place=None` on a self-move means withdrawal from the battle.
_Avoid_: reposition (reserved for the vehicle-coordinate verb), retreat (use
"withdraw"/"withdrawal" — the `WITHDRAWN` status name).

**Reposition** (verb):
The `BattleActionKind.REPOSITION` declaration (#1714) — moves a `BattlePlace`'s own
`x`/`y` coordinates (the battle-map plane, ADR-0085), clamped to the target
vehicle's SPEED capability. Vehicle-commander-gated only (bypasses Command Tier
entirely — a non-covenant-backed vessel must still be movable). Distinct from
**Move** above, which relocates a participant/unit between existing places rather
than moving a place itself.
_Avoid_: move (reserved for the participant/unit-relocation verb).

**Transit**:
`transit_x`/`transit_y`/`transit_target_place` (#2007) — a `BattleParticipant`'s or
`BattleUnit`'s in-progress position while a multi-round **Move** hasn't yet
completed. All three null means "at rest" (effective position is simply the
mover's current `.place` coordinates). Cleared on arrival or withdrawal.
_Avoid_: en route, mid-move (descriptive only, not model vocabulary).

**Fortification**:
A `Fortification` — a defensible structure (wall/gate/battlement) at a
`BattlePlace` (#1713). A front may carry several at once, each independently
breachable via its own `integrity`/`max_integrity` — see ADR-0083 for why this
is per-structure state rather than a single shared value on `BattlePlace`
itself (mirroring `BattleUnit.strength`). `defending_side` gates which side may
BREACH (must differ) vs FORTIFY (must match) it. `breached` is terminal — once
set, the structure can no longer be targeted by either verb.
_Avoid_: wall (too narrow — a `Fortification` may be a gate or battlement),
objective (reserved for the front-control sense, see **Front control** above).

**Breach** (verb):
The `BattleActionKind.BREACH` declaration (#1713) — attrites a target
`Fortification`'s `integrity`, awarding VP; sets `breached=True` at 0. Must
target the enemy's structure (`FortificationOwnershipMismatchError` otherwise).

**Fortify** (verb):
The `BattleActionKind.FORTIFY` declaration (#1713) — restores a target
`Fortification`'s `integrity` (capped at `max_integrity`), awarding flat VP.
Must target your own side's structure. Distinct from **Front control**'s HOLD —
FORTIFY repairs a structure's integrity, HOLD captures/sustains a front.

**Fortification level**:
`world.buildings.Building.fortification_level` (#1713, cross-app) — a
persistent, player-built defense investment raised via a `FORTIFICATION_UPGRADE`
Project, snapshotted once into a new `Fortification`'s `max_integrity` by
`create_fortification`. Distinct from the battle-scoped `Fortification` model
above: this is the durable investment that seeds a `Fortification`'s starting
ceiling, not the per-battle structure itself. See `world.buildings`'s own
glossary entry for the buildings-side detail.

**Victory Points**:
`BattleSide.victory_points` — the accumulating score each side races toward
its `victory_threshold`. Award-only in every existing action kind (STRIKE,
SUPPORT, ROUT, RALLY, REPEL, HOLD, BREACH, FORTIFY) — no action denies/subtracts
VP from a side (#1712 considered and explicitly deferred a denial mechanic).

**Descriptor**:
A `BattleUnit`'s free-text flavor tag (e.g. "zombies-on-nightmares"); narrative only,
never mechanical — `properties`/`capabilities`/`quality` drive mechanics. Renamed from
the spine's `unit_type` (#1711).

**Commander (unit)**:
The `CharacterSheet` assigned to `BattleUnit.commander` (#1711); their Battle Command
modifier-walk bonus applies to participants fighting alongside this unit's side/place.
Distinct from Command Tier below (covenant-role hierarchy, #1710) — a unit commander
need not hold any `CovenantRole` at all.
_Avoid_: leader (reserved — `Covenant.leader` is a distinct, COURT-only concept),
general.

**Type-matchup**:
A `TechniquePropertyAffinity` row (#1794, replacing #1711's
`TechniqueCompositionAffinity`): a technique's authored effectiveness against a specific
`Property`. Summed across every property a target unit carries, rather than matched
against one composition tag.

**Terrain effect**:
A `TerrainPropertyEffect` row (#1794, replacing #1711's `TerrainCompositionEffect`): a
`BattlePlace`'s `TerrainType`'s authored effect on a specific `Property`'s
ease-of-strike. Summed across every property a target unit carries.

**Military summon**:
A `summon_ally` cast with `payload.military=True` (#1711): creates a `BattleUnit`
(not a `CombatOpponent`) for a summon too potent for a skirmish. See
`_summon_military_unit` in `world.magic.services.effect_handlers`.

**Command Tier**:
The battle-command hierarchy axis of a `CovenantRole` (`CovenantRole.command_tier`,
#1710): `NONE`/`SUBORDINATE`/`SUPREME`. Settable only on `CovenantType.BATTLE` roles.
Exactly one engaged `SUPREME` role per covenant (the Supreme Commander); any number
of engaged `SUBORDINATE` roles (Subordinate Commanders). Orthogonal to
`covenants.CovenantRank` (administrative authority) — see that app's glossary.
_Avoid_: rank, leader, is_leadership (removed under #1027).

**Supreme Commander**:
The single covenant member holding an engaged `CovenantRole` with
`command_tier=SUPREME` for their covenant. Can declare army-scale
(`BattleActionScope.SIDE`) battle-round actions.
_Avoid_: warlord, general (flavor labels only, no model surface).

**Subordinate Commander**:
A covenant member holding an engaged `CovenantRole` with `command_tier=SUBORDINATE`.
Not exclusive — multiple may exist per covenant. Can declare front-scale
(`BattleActionScope.PLACE`) battle-round actions.

**The Champion**:
The single covenant member holding an engaged `CovenantRole` with
`is_champion_role=True` (#1710). Can open a lethal `CombatEncounter` duel
(`open_champion_duel`) against a significant enemy NPC, bound to a `BattlePlace`.
_Avoid_: hero, duelist (descriptive only).

**Declaration Scope**:
`BattleActionDeclaration.scope` (`UNIT`/`PLACE`/`SIDE`, #1710) — the targeting
breadth of a declared battle-round action. `PLACE`/`SIDE` require the matching
Command Tier on the declaring participant's side's covenant.
_Avoid_: range, radius, AOE.

**BATTLE_STATE ping**:
The `BattleStatePayload` (#2009, `web.webclient.message_types`) WS message —
`{battle_id, round_number}` only, no battle data. Sent to connected
participants from `notify_battle_state_changed` (`world.battles.services`)
after `begin_battle_round`/`resolve_battle_round`/`conclude_battle`, deferred
via `transaction.on_commit`. A slim "go refetch" signal, not a state push —
the frontend treats receipt as cache invalidation only (`battleKeys.all`),
then reads the real state back from `GET /api/battles/<pk>/`
(`BattleDetailSerializer`). See ADR-0095.
_Avoid_: battle update, state push (implies the payload itself carries state).

**Battle-Map Blueprint**:
A `BattleMapBlueprint` (#2010) — a reusable, admin-authored catalog row a JUNIOR-trust
GM stages a `Battle`'s map from, rather than inventing terrain/fortification layouts
from scratch. Owns `BlueprintBattlePlace`/`BlueprintFortification` rows — catalog-time
counterparts to `BattlePlace`/`Fortification` — copied onto a live `Battle` by
`instantiate_battle_blueprint`. See ADR-0111.
_Avoid_: battle template, setup wizard (this is a catalog row a GM picks and copies,
not an authoring flow).

**Unit Template**:
A `BattleUnitTemplate` (#2010) — a reusable, admin-authored catalog stat block (quality/
strength/morale/properties/capability values) a JUNIOR-trust GM spawns one or more
`BattleUnit`s from via `spawn_units_from_template`, rather than authoring a unit's stat
block from scratch each time. Catalog-time counterpart to `BattleUnit`, mirroring
**Battle-Map Blueprint**'s shape.
_Avoid_: army preset, unit preset (implies a bundled army composition, not a single
reusable stat block).

**Staging**:
The JUNIOR-trust GM workflow (#2010) that turns a catalog pick (**Battle-Map
Blueprint** / **Unit Template**) into a live `Battle`: `create_battle` (optionally
cloning a blueprint in the same call) → `stage_battle_map` / `spawn_battle_units` →
`enlist_battle_participant`, discoverable via `browse_battle_catalog`. Wraps
`world.battles.staging`'s services (`stage_battle`/`instantiate_battle_blueprint`/
`spawn_units_from_template`); never accepts free-form terrain/fortification/unit-stat
authoring at stage time (ADR-0110, ADR-0111).
_Avoid_: setup wizard (implies a bespoke multi-step authoring UI, not a catalog-pick
action pipeline), army preset (see **Unit Template**).
