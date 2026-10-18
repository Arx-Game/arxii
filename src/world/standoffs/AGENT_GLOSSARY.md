# Standoffs glossary

**Standoff** (#4145, ADR-4145-A):
The pre-round state of a `CombatEncounter`: round zero while at least one `StandoffGroup` is OPEN or PROPOSED. Derived (`is_in_standoff`), never a stored flag. The party may read the groups and press or name terms to them; it ends when the party chooses to fight, a group's cause fires, a GM or cast begins round one, or every group is settled (an ordinary VICTORY).
_Avoid_: parley phase, negotiation, pre-combat, stand-off (hyphenated)

**Group** (standoff group, `StandoffGroup`):
One band of opponents sharing a `CreatureTemplate` within one standoff, or one Named NPC group, with its own state (OPEN, PROPOSED, SETTLED, FIGHTING), `terms_ease` and `emboldened_bands`. Membership is the ACTIVE opponents of that template standing as no persona, or the opponent standing as the group's persona; a group with none left is SETTLED.
_Avoid_: faction, squad, pack

**Named NPC group** (`StandoffGroup.persona`, #4373):
A group of one: an opponent standing as a `Persona`, read, pressed and settled on its own and named by the persona. Its drives are the persona's properties; its `NpcRegard` for the acting character's presented persona eases or hardens presses and terms.
_Avoid_: boss group, persona opponent (the opponent is a `CombatOpponent` with a persona), hero

**Language gate** (`StandoffApproach.is_verbal`, `CreatureTemplate.language`, #4373):
A verbal approach, or terms, is refused when the group shares no language with the actor (a group with no language at all refuses verbal approaches only). Read is never gated. Refused entries stay listed with the reason.
_Avoid_: translation, fluency check (no roll is made), comprehension roll

**Drive** (`CreatureDrive`):
What a kind of creature wants, as a property (for example Greedy) with a `DriveStrength` (Minor, Major, Defining). An approach whose capability has an Application aimed at that property "hits" the drive and eases the grade by its strength in bands.
_Avoid_: motive (a Reaction owner's "Enemy reason" owns that word), want, desire

**Cause** (`CreatureTemplate.cause`, `CauseKind`):
Why a kind of creature picks a fight on its own when nothing else moves it. Predation fires when the party's force does not outweigh the group's by `cause_margin_percent`. Orders fires the same way, and also on a provocation (a botched press or terms against the group). Hunger (#4415) is Predation with the margin widened by `StandoffConfig.hunger_margin_step` for every party action that passed. Hatred (#4415) never fires on force: only a participant matching a faction rule that provokes them sets them off, until the group breaks. Territory (#4415) fires once the party has taken `territory_patience` actions without settling or leaving, and warns the room one action earlier. A matched suppressing rule for every participant stops any cause but a provocation by rule. In a GM-run standoff a firing cause becomes a Proposal; the fight then begins with `initiated_by_pc_side=False`.
_Avoid_: aggression, hostility flag, motive

**Cause effect** (`FactionRule.cause_effect`, `CauseEffect`, #4415, was `suppresses_cause`):
What a matched faction rule does to the group's cause: None, Suppress (they will not start the fight while every participant matches one), or Provoke (a participant who matches one sets them off, whatever the force, unless the group is broken). The most specific rule with an effect decides for each character; at one level Provoke beats Suppress.
_Avoid_: aggro, trigger (a flows term), taunt

**Clock** (`StandoffGroup.actions_elapsed`, #4415):
The count of party actions (read, press, terms, share) taken while a group stood in the standoff. Hunger's margin and Territory's patience run on it; arrival and GM controls do not move it. The GM view shows it as "Hunger margin N%" or "Patience: N of M actions".
_Avoid_: timer, turn counter (a standoff has no rounds), patience meter

**Broken-hold re-test** (`retest_cause_on_release`, #4415, ADR-4415-A):
When a Calm or Charmed hold on an opponent ends (broken, settled or lapsed) in an encounter still running, its cause is asked again. It does not hold: the NPC leaves (FLED). It holds: a settled group re-enters the standoff and its cause fires (a Proposal where a GM runs the scene), or, once the fight is under way, the NPC fights on. Terms a group accepted meet an Orders, Hunger or Territory cause.
_Avoid_: re-aggro, hostility restart, relapse

**Faction** (#4121):
How a group views a character, following the character's reputation with an organization or society and their visible association with one, through the group's faction rules. Not which side an opponent fights on (that is Allegiance).
_Avoid_: allegiance, side

**Faction rule** (`FactionRule`, was Regard rule; renamed #4354):
How a group stands toward particular characters: a predicate over the acting character's own state (plus a typed `deed_archetype` for deeds they are commonly known for) that can shift difficulty bands, shift a drive's strength, or suppress or provoke the cause (its Cause effect). It carries an owner-only angle and a revealed text. Owned by a creature template, an organization or a society (#4361); a group carries its template's rules and those inherited through its Affiliation, and where two shift the same thing the most specific owner wins.
_Avoid_: regard rule (`NpcRegard` is one named NPC's own opinion, a different thing), reaction (Reaction Line and Reaction Economy are other systems), social profile, reputation modifier

**Angle** (`FactionRule.angle_text`, was Spark; renamed #4354):
What a matched character privately learns matters about them here, because a faction rule applies to them. Shown only to that character; the player chooses when the table learns it (Share), or it is shared by acting on it. Recorded as `StandoffAngleShare`.
_Avoid_: spark, hook (a Trigger is a flows term), ask (a Boon), aura (a resonance aggregate)

**Association** (`associated_with_org`, `associated_with_society`, #4361):
Being seen as tied to an organization or society: membership now or before (a former member for `AssociationConfig.former_member_years`, an exile always), kinship with a family house, or steady work for its people. Covert organizations never count; only the presented persona is read. What a faction rule may test besides reputation.
_Avoid_: membership (the formal row), reputation (how the organization itself regards you)

**Affiliation** (`CreatureTemplate.organization`, a placement's `organization`, #4361):
The organization a group's faction rules are inherited through: its own rules, each parent organization's and each of their societies'. A template carries a default; a placement may name another.
_Avoid_: allegiance (which side an opponent fights on), membership (a persona's formal row), faction (how a group views a character)

**Placement** (`BeatOpponentLine`, `MissionOptionOpponentLine`, #4361):
One authored opponent line, and the edits it makes over its creature template: cause, margin, affiliation, drives and switched-off inherited faction rules. Stamped on each opponent at spawn (ADR-4361-A).
_Avoid_: spawn (the act), instance, override (one kind of edit a placement makes)

**Proposal** (`StandoffGroupState.PROPOSED`, #4354):
In a GM-run standoff, a group whose cause fired waits in PROPOSED while a `STANDOFF_CAUSE` GM prompt asks the GM to Confirm (the fight begins), Hold for one action, or Override with a reason. Players keep acting meanwhile and see the group marked "deciding". A standoff is GM-run when its scene has a GM who has not muted standoff prompts; otherwise causes fire on their own.
_Avoid_: suggestion (a dramatic-moment prompt), vote, pending attack

**Terms** (`StandoffTerms`):
What a party names to a group to end its part of the standoff, with a `TermsEffect` (PASS, FLEE, TURN, TOLL), an optional required drive that must be read first, and a difficulty shift. A partial or better success settles the group.
_Avoid_: ask, offer, deal, demand

**Approach** (`StandoffApproach`):
A way of pressing a group: a check type, a capability that aims at drives, an optional sway modifier target, and whether it damages morale. A success adds `terms_ease`; a botch emboldens the group.
_Avoid_: sway (an Application name), lever (the player-facing word for a revealed drive an approach hits), tactic

**Read** / **Press**:
Read is the check that reveals one hidden thing about a group (cause, drive or faction rule): a partial reveals one at random, a success the one the reader chose, a critical everything. Press is a social approach that eases terms. Both are verbs of `world/standoffs/services/verbs.py`.
_Avoid_: consider (a Consider read is a level-band concept in combat), probe (a combat health read), persuade

**Reaction line (standoff)** (`StandoffReactionLine`):
Staff-authored room text for how a press or terms roll lands, banded by success level (highest floor at or below the roll wins; a creature-specific line beats a generic one at the same floor). It replaces the plain outcome line for that action.
_Avoid_: NPC reaction line (`NPCReactionLine` is a different thing: an NPC role's line banded on the served character's allure or menace), flavour text, barks

**Profile** (player character, `CharacterStandoffProfile`, #4441, ADR-4441-A):
A player's own standoff entry for their character: whether other player characters may read and press them (`opted_in`), a cause and drives picked from the creature catalogs. Only an opted-in player character can be a group. It cannot change while the character stands in a standoff.
_Avoid_: creature template (shared authored content), flag, consent form
