# Combat glossary

**CombatEncounter**:
The top-level container for one fight — an `AbstractRound` subclass carrying its required scene, room, encounter type, risk level, stakes, and typed outcome. It owns the participants, opponents, clashes, and per-round action ledger.
_Avoid_: battle, fight (as a model name), combat session

**CombatParticipant**:
A PC's enrolment in a `CombatEncounter` (one per character per encounter), tracking status (active/fled/removed), covenant role, and the character's per-round strain budget.
_Avoid_: combatant, fighter, player (for the PC's encounter row)

**CombatOpponent**:
An NPC entity in a `CombatEncounter`, defined by its `OpponentTier`, health/soak/probing stats, threat pool, and (for bosses) phases. The NPC analogue of a `CombatParticipant`.
_Avoid_: enemy, monster, mob, NPC participant

**Maneuver**:
A special non-technique declaration a PC can make for a round (`CombatManeuver`: FLEE, COVER, YIELD, INTERPOSE) — a verb that is neither a technique cast nor a clash commit. Each is a real Action on the shared dispatch seam.
_Avoid_: special move, stance, command

**Yield**:
The maneuver by which a PC concedes — in a duel the yielding PC loses immediately. PvP is structurally non-lethal (yield / knockout), so yielding ends the contest without injury or death.
_Avoid_: surrender, forfeit, submit, defeat

**Interpose**:
The maneuver by which a PC stands ready to step in front of an attack aimed at an ally and intercept it (a clean block). It costs fatigue only on the round it actually fires; an armed-but-never-triggered interpose costs nothing.
_Avoid_: block, guard, intercept, bodyguard

**Clash**:
The reserved combat primitive for a multi-round contest in which two sides pour magical energy into overpowering each other (the "beam-struggle" trope) — the clash of wills. Modelled by `Clash` with a flavor discriminator (CLASH / LOCK / WARD / BREAK). The word "clash" is reserved for this feature and must not name any other concept.
_Avoid_: contest, struggle, beam struggle; backfire / rejection / dissonance for unrelated opposing-resonance effects

**Strain**:
Anima a PC commits beyond a technique's effective cost floor, converted by a diminishing-returns curve (`StrainConfig`) into a power/intensity bonus passed to the cast. Strain scales the technique's power and progress delta — never the check roll.
_Avoid_: push, overcharge, effort (effort modifies the roll; strain scales power)

**CombatPull**:
A per-(participant, round) commit envelope capturing the resonance, tier, and threads a participant spends on a thread pull during combat. Resolved effects are snapshotted so mid-round authoring edits cannot retroactively change a committed pull.
_Avoid_: thread pull (the in-combat record specifically), draw

**ThreatPool**:
A named collection of the possible actions an NPC can take in a round (`ThreatPoolEntry` rows); a boss phase or opponent draws its behaviour from its assigned pool.
_Avoid_: action list, move set, aggro pool

**BossPhase**:
One stage of a boss fight (`BossPhase`) with its own threat pool, soak, probing threshold, and health trigger; a boss progresses through its phases as its health crosses each trigger.
_Avoid_: stage, form, tier (tier is the opponent's power class)

**OpponentTier**:
The power class of an NPC opponent (`OpponentTier`: SWARM, MOOK, ELITE, BOSS, HERO_KILLER), seeding its baseline stat budget. SWARM uses count/body-toughness mechanics; HERO_KILLER is the unbeatable presence.
_Avoid_: rank, level, difficulty (for the NPC's class)

**Party Profile**:
An immutable level-only snapshot of the active party (`PartyProfile`: party_size + avg_level) feeding the encounter-scaling formula. Difficulty scales on party size and average level only — never on threads, relationships, or other narrative richness.
_Avoid_: party stats, party power, party rating

**Focused action**:
The single primary action a PC commits in a round — the one that matches a combo slot and carries the round's main intent. A round is one focused action plus up to two secondary actions.
_Avoid_: main action, primary (use "focused" specifically)

**Secondary action**:
A supporting action a PC takes alongside the focused action (physical and/or social), up to two per round. The non-focused action type.
_Avoid_: passive
