# ADR-4581-A: A vow added effect never alters behavior, and an upgrade replaces the row it names

**Date:** 2026-10-22
**Status:** Accepted (maintainer, on #4573)
**Issue:** #4581 (relates #4573)

## Decision

A covenant vow adds staff-authored effects to technique casts through `VowAddedEffect`
and its four payload children (applied conditions, removed conditions, treatments,
damage). A vow added effect never applies a behavior-altering condition (compulsion,
charm, fear): `VowAddedEffectAppliedCondition.clean()` refuses any condition whose
category `alters_behavior`. Consent for such a condition is decided before resolution,
from the caster's own signature (`world/magic/services/targeting.py` folds only the
caster's own rows), and a caster cannot predict the rows of another holder's vow that
will ride the same cast. Holding the rule at authoring time keeps that consent
calculation true without touching it.

Among a holder's rows, every row adds, except where one names another through
`VowAddedEffect.upgrades`: a resonance sub-role's version of its parent role's row, or
a later-unlock row on the same role. When the holder qualifies for both, the upgrade
replaces the base, and that happens before the once-per-round or once-per-fight limit is
read, so a spent upgrade still suppresses its base. The FK is `RESTRICT`: deleting a
role still cascades its own base and its own upgrade, but a base that another role's row
upgrades cannot be deleted out from under it.

## Rejected

Extending consent folding to every co-present holder's rows: it would make a cast's
consent depend on who else is in the room and what they have sworn, and the fold runs
before the cast resolves. Matching upgrades by shape (same function, same payload) is
ambiguous, and by name is banned by the never-match-a-name rule. A new
`VowSituationalPerk` kind: a perk carries a numeric magnitude and a required prose
`announce_template`, six columns only one kind reads, none of which a payload row uses.
A boolean per row on `CombatParticipant` for the limits: it cannot scale with the number
of authored rows or hold a per-round count, so the `VowAddedEffectFiring` ledger replaces
it.
