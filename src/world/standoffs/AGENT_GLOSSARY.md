# Standoffs glossary

**Standoff** (#4145, ADR-4145-A):
The pre-round state of a `CombatEncounter`: round zero while at least one `StandoffGroup` is OPEN. Derived (`is_in_standoff`), never a stored flag. The party may read the groups and press or name terms to them; it ends when the party chooses to fight, a group's cause fires, a GM or cast begins round one, or every group is settled (an ordinary VICTORY).
_Avoid_: parley phase, negotiation, pre-combat, stand-off (hyphenated)

**Group** (standoff group, `StandoffGroup`):
One band of opponents sharing a `CreatureTemplate` within one standoff, with its own state (OPEN, SETTLED, FIGHTING), `terms_ease` and `emboldened_bands`. Membership is the ACTIVE opponents of that template; a group with none left is SETTLED.
_Avoid_: faction, squad, pack

**Drive** (`CreatureDrive`):
What a kind of creature wants, as a property (for example Greedy) with a `DriveStrength` (Minor, Major, Defining). An approach whose capability has an Application aimed at that property "hits" the drive and eases the grade by its strength in bands.
_Avoid_: motive (a Reaction owner's "Enemy reason" owns that word), want, desire

**Cause** (`CreatureTemplate.cause`, `CauseKind`):
Why a kind of creature picks a fight on its own when nothing else moves it. Predation fires when the party's force does not outweigh the group's by `cause_margin_percent` unless every active participant matches a regard rule that suppresses it; the fight then begins with `initiated_by_pc_side=False`.
_Avoid_: aggression, hostility flag, motive

**Regard rule** (`RegardRule`):
How a kind of creature regards particular characters: a predicate over the acting character's own state (plus a typed `deed_archetype` for deeds they are commonly known for) that can shift difficulty bands, shift a drive's strength, or suppress the cause. It carries an owner-only spark and a revealed text.
_Avoid_: reaction (Reaction Line and Reaction Economy are other systems), social profile, reputation modifier

**Spark** (`RegardRule.spark_text`):
What a matched character privately feels about a group because a regard rule applies to them. Shown only to that character; the player chooses when the table learns it (Share), or it is shared by acting on it. Recorded as `StandoffSparkShare`.
_Avoid_: hook (a Trigger is a flows term), ask (a Boon), aura (a resonance aggregate)

**Terms** (`StandoffTerms`):
What a party names to a group to end its part of the standoff, with a `TermsEffect` (PASS, FLEE, TURN, TOLL), an optional required drive that must be read first, and a difficulty shift. A partial or better success settles the group.
_Avoid_: ask, offer, deal, demand

**Approach** (`StandoffApproach`):
A way of pressing a group: a check type, a capability that aims at drives, an optional sway modifier target, and whether it damages morale. A success adds `terms_ease`; a botch emboldens the group.
_Avoid_: sway (an Application name), lever (the player-facing word for a revealed drive an approach hits), tactic

**Read** / **Press**:
Read is the check that reveals one hidden thing about a group (cause, drive or regard): a partial reveals one at random, a success the one the reader chose, a critical everything. Press is a social approach that eases terms. Both are verbs of `world/standoffs/services/verbs.py`.
_Avoid_: consider (a Consider read is a level-band concept in combat), probe (a combat health read), persuade

**Reaction line (standoff)** (`StandoffReactionLine`):
Staff-authored room text for how a press or terms roll lands, banded by success level (highest floor at or below the roll wins; a creature-specific line beats a generic one at the same floor). It replaces the plain outcome line for that action.
_Avoid_: NPC reaction line (`NPCReactionLine` is a different thing: an NPC role's line banded on the served character's allure or menace), flavour text, barks
