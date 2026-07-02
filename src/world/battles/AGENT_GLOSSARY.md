# Battles glossary

**Battle**:
A large-scale multi-party engagement, a 1:1 extension of `scenes.Scene`. Owns
`BattleSide`s, `BattlePlace`s (fronts), abstract `BattleUnit`s, and per-round
`BattleActionDeclaration`s.
_Avoid_: encounter, fight (use `CombatEncounter` for a discrete tactical fight).

**Battle Side**:
One faction in a `Battle` (`ATTACKER`/`DEFENDER`) with its own victory-point tally.
Optionally fielded by a War Covenant (`BattleSide.covenant`, #1710) — a side with no
covenant has no command hierarchy.
_Avoid_: team, faction (use "side").

**Battle Place**:
A named front/zone within a `Battle` (e.g. "The Main Gates"). Can be bound to a real
`CombatEncounter` (`combat_encounter` FK) for a discrete tactical fight at that
front — most commonly a Champion duel (#1710).
_Avoid_: front (descriptive only), zone, location.

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
