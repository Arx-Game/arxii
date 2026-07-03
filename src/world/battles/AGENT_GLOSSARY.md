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
(`combat_encounter` FK) for a discrete tactical fight at that front — most commonly a
Champion duel (#1710).
_Avoid_: front (descriptive only), zone, location.

**Unit**:
A `BattleUnit` — an abstract typed force (friendly or enemy) stationed at a place.
Carries `properties` (a plain M2M to the same `Property` catalog characters use — see
`world/mechanics/AGENT_GLOSSARY.md`'s **Property** entry; presence-only tags like
flying/aquatic/metal-clad, #1794) driving type-matchups and terrain effects, and
`capabilities` (M2M to `CapabilityType` through `BattleUnitCapability`, an authored
per-unit magnitude — two units can hold the same capability at very different values,
#1794). Also carries a `UnitQuality` tier (militia through elite, #1711) — a flat
check-difficulty modifier ladder, not a strength multiplier — and an `individual_count`
(nullable population data point mirroring `CombatOpponent.swarm_count`, #1794; no
swarm-math wired against it yet). Replaces the spine's single-select `UnitComposition`
enum (#1711), which could only ever tag a unit with one composition.
_Avoid_: squad, regiment, mob; composition (superseded term — use properties/capabilities).

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
