# ADR-0211: Predators are a thin dedicated model on a slow menace ladder

**Status:** Accepted (#3093, 2026-08-10)

NPC antagonists (bandit companies, pirate fleets, raider warbands) are a
dedicated lightweight model (`PredatorBand` + authored `PredatorKind`), NOT
`Organization` rows — Apostate's explicit ruling: Organization is structurally
the *player-holding* construct (ranks, memberships, offers, reputation), and a
pure antagonist will never take a member, so reusing it drags dead structure
and invites accidental coupling. The band carries only what predation needs:
strength, loot, prey, home region, and a **menace stage**. Escalation is
deliberately slow — roughly ten weekly crons from first rumor to an actual
raid, through small legible steps (rumors → lawlessness → robbery → raids →
terror), each announced in the tidings, advancing only while *unanswered*;
any counterplay knocks the ladder down and burns strength. Players must
always have time to see it coming and respond. Afflictions share the app and
the same principle (a SIGNS week precedes every outbreak; spread is slow and
capped) but ignore stature entirely — deterrence means nothing to the dead.
Rejected: Organization reuse (above); a `MilitaryUnit`-backed strength
(battle machinery stays the battles system's; a simple integer suffices until
positional warfare needs more); instant-escalation raid spawns (the #3091
ambient roll already covers random shocks — named actors exist precisely to
be watched, dreaded, and hunted over months).
