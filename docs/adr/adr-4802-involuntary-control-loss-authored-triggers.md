# ADR-4802: Losing control is one mechanism with authored triggers, and a compulsion rolls instead of refusing

**Status:** Accepted (built #4802; supersedes ADR-0183)

**Decision.** Losing control without choosing to is one mechanism. A character carries a
vulnerability condition (Lycan blood, a curse). Authored `ControlLossTrigger` rows hang off
it and fire on the moon's pull, a wound crossing a health threshold, or the condition
entering a stage. A fired trigger rolls its check and applies the `ControlLossBand` for the
outcome (an engagement shift, a condition such as Berserk, a forced form). The moon is one
trigger row among the others, with its numbers in the database and no code of its own. The
condition that takes control carries a `Compulsion`: what it wants (today, attacking an
opponent), its resist check, the actions it forbids and each one's extra difficulty, and
`CompulsionResistBand` rows saying what each roll outcome does. Nothing is refused. Every
action stays declarable, and anything other than what the compulsion wants rolls the resist
check at the round lock. A good result acts freely, a middling one acts at a penalty, and a
bad one lets the compulsion replace the action with an attack. Leaving the encounter and
changing form back roll the same check. An ally with the steadying capability can spend
anima and a reaction to give the compelled fighter a second roll. Player characters roll;
NPCs never do. **Why:** the owner ruled that very few things are a flat "no", that the moon
must not be special, and that staff add new ways to lose control by authoring rows. A
refusal also left a berserker no play, and gave a supporter nothing to do about it.

**Rejected alternatives.** (a) A moon-only special case with the tuning in code, as
ADR-0183 built it: each new source of lost control would need its own code and its own
refusals. (b) Compulsions as declaration locks, where the engine refuses the forbidden
action outright: that is the behaviour being removed, and it leaves nothing to resist.
