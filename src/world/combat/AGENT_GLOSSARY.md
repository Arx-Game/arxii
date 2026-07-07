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
A special non-technique declaration a PC can make for a round (`CombatManeuver`: FLEE, COVER, YIELD, INTERPOSE, SUCCOR) — a verb that is neither a technique cast nor a clash commit. Each is a real Action on the shared dispatch seam.
_Avoid_: special move, stance, command

**Yield**:
The maneuver by which a PC concedes — in a duel the yielding PC loses immediately. PvP is structurally non-lethal (yield / knockout), so yielding ends the contest without injury or death.
_Avoid_: surrender, forfeit, submit, defeat

**Interpose**:
The maneuver by which a PC stands ready to step in front of an attack aimed at an ally and intercept it (a clean block). It costs fatigue only on the round it actually fires; an armed-but-never-triggered interpose costs nothing. See `world/scenes/AGENT_GLOSSARY.md`'s Sudden Harm entry for the out-of-combat sibling, which arms via a bootstrapped scene round instead of a `CombatRoundAction`.
_Avoid_: block, guard, intercept, bodyguard

**Succor**:
The maneuver by which a PC shelters a specific ally from a round-ticked environmental hazard (sunlight, poison gas) this round — the environmental-DoT sibling of Interpose (which blocks an incoming attack, not a lingering hazard). Always names a specific ally; there is no "any ally" path like Interpose has, since environmental shelter is "I'm sheltering THIS person," not "I'll block whichever hazard lands on someone." Resolves through the same graded capability-check spine as Interpose.
_Avoid_: shelter (as the maneuver name), cover, shield, protect

**Clash**:
The reserved combat primitive for a multi-round contest in which two sides pour magical energy into overpowering each other (the "beam-struggle" trope) — the clash of wills. Modelled by `Clash` with a flavor discriminator (CLASH / LOCK / WARD / BREAK). The word "clash" is reserved for this feature and must not name any other concept.
_Avoid_: contest, struggle, beam struggle, push (colloquial in code for Clash's tug-of-war progress — see `clash.py` — but ambiguous with Strain and Knockback; prefer "clash"); backfire / rejection / dissonance for unrelated opposing-resonance effects

**Dramatic Surge**:
A discontinuous, one-shot jump to `CharacterEngagement.intensity_modifier` at a dramatic combat beat — a bonded ally entering mortal peril, a hated NPC foe entering the fight, or a high-stakes encounter igniting — written through the single shared `apply_dramatic_surge` primitive and deduped per (encounter, participant, trigger kind, subject) via `DramaticSurgeRecord`. Narrated generically in the combat log; never names the bond, track, or subject.
_Avoid_: clash (reserved, see above), spike (ambiguous with the pre-existing #872 grief "spike" internals — "surge" is the player-facing term), burst, power-up

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

**Allegiance**:
Which side a `CombatOpponent` fights on — `ENEMY` (hostile to PCs, the default) or `ALLY`
(fights for the party). Allegiance is mutable: a summon spell creates an ALLY opponent; future
charm / switch-sides effects flip an existing ENEMY to ALLY. Both cases use the same field on
the same model; no parallel model is needed (ADR-0059).
_Avoid_: faction, team, side (as model names)

**Summon**:
An ALLY `CombatOpponent` conjured during combat by a technique. It has `allegiance=ALLY`,
`summoned_by` (FK → `CharacterSheet`), and `bond_expires_round`; it attacks ENEMY opponents
via `CombatOpponentAction.opponent_targets`. "Summon" means this specific bonded ALLY; the
general concept of a combat companion is "ally combatant".
_Avoid_: familiar, pet, companion (for the in-combat summon row specifically)

**Reactive interceptor**:
A mutation-only `DAMAGE_PRE_APPLY` flow handler that can reduce or nullify an incoming hit —
force-field (absorb_pool, priority 10), reflect (reflect_damage, priority 20), or blink
(blink_dodge, priority 30). Each sets `payload.amount = 0` on success; lower-priority
interceptors guard `if payload.amount <= 0: return`. Cost: `reactive_anima_cost` per fire;
can't pay → fizzle, attack lands. No `CANCEL_EVENT` child step (ADR-0060).
_Avoid_: cancel-event interceptor, reactive cancel, shield handler

**Knockback**:
A deterministic on-hit effect that shoves the defender one Position away from the attacker, authored via `ThreatPoolEntry.on_hit_consequence_pool` firing a `MOVE_TO_POSITION`/`AWAY_FROM_ACTOR` consequence effect. Fires only after the #1273 Interpose seam resolves — a clean block prevents it for free.
_Avoid_: push ("push" is already ambiguous with Strain and Clash's tug-of-war progress — see those entries), shove, displace
