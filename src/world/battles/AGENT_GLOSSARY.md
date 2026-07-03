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
location-less (see ADR-0081). Carries a `TerrainType` (#1711) affecting composition
matchups. Can be bound to a real `CombatEncounter` (`combat_encounter` FK) for a
discrete tactical fight at that front — most commonly a Champion duel (#1710).
_Avoid_: front (descriptive only), zone, location.

**Unit**:
A `BattleUnit` — an abstract typed force (friendly or enemy) stationed at a place.
Carries a `UnitComposition` (infantry/cavalry/archers/siege/flying/naval/magical/
irregular, #1711) driving type-matchups and terrain effects, and a `UnitQuality` tier
(militia through elite, #1711) — a flat check-difficulty modifier ladder, not a
strength multiplier.
_Avoid_: squad, regiment, mob.

**Descriptor**:
A `BattleUnit`'s free-text flavor tag (e.g. "zombies-on-nightmares"); narrative only,
never mechanical — `composition`/`quality` drive mechanics. Renamed from the spine's
`unit_type` (#1711).

**Commander (unit)**:
The `CharacterSheet` assigned to `BattleUnit.commander` (#1711); their Battle Command
modifier-walk bonus applies to participants fighting alongside this unit's side/place.
Distinct from Command Tier below (covenant-role hierarchy, #1710) — a unit commander
need not hold any `CovenantRole` at all.
_Avoid_: leader (reserved — `Covenant.leader` is a distinct, COURT-only concept),
general.

**Type-matchup**:
A `TechniqueCompositionAffinity` row (#1711): a technique's authored effectiveness
against a specific `UnitComposition`.

**Terrain effect**:
A `TerrainCompositionEffect` row (#1711): a `BattlePlace`'s `TerrainType`'s authored
effect on a specific `UnitComposition`'s ease-of-strike.

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
