# ADR-0126: A mount is a companion plus a verb-gating condition; charge/joust ride the existing move/duel seams

**Status:** Accepted (2026-07-12) · **Issue:** #1843

A mount is a `Companion` whose archetype has `is_mount=True` — no new typeclass, no
parallel "vehicle" model. Riding state is `Companion.ridden_by` (a nullable **unique**
FK → `CharacterSheet`, enforcing one rider per mount at the DB level) plus a seeded
"Mounted" `ConditionTemplate` applied/removed by `mount_companion`/`dismount_companion`
(`world.companions.services`). Mounted carries **zero passive check bonuses** — it is
pure state other code branches on (`has_condition`), gating exactly two new combat
verbs: `CombatManeuver.CHARGE` (mounted charge — force-moves the rider onto a
1+-hop-away opponent's position via the existing room-positioning primitives, then
resolves as a normal weapon attack with flat `CHARGE_CHECK_BONUS`/`CHARGE_DAMAGE_BONUS`
folded into `CombatTechniqueResolver`'s existing modifier/damage-budget seams, doubled
for an equipped `GearArchetype.LANCE`) and `CombatManeuver.JOUST` (a mounted,
lance-armed opposed pass, only declarable in a 2-participant DUEL where both sides hold
Mounted and have a LANCE equipped — resolved as one pair of opposed checks via the same
resolver seam, graded by the `success_level` gap into decisive/narrow/tie bands, with
damage applied to the loser's mirror `CombatOpponent` through the pre-existing
non-bypassing duel-damage path so ADR-0023's non-lethal PvP cap and every defense/
guardian/rampart hook keep firing unchanged). `LANCE_UNMOUNTED_PENALTY` gates any
LANCE-archetype attack made without Mounted, at the same check-modifier seam.

Rejected alternatives: (1) **Mount as its own typeclass/model** — companions already
have a live `objectdb`, capacity accounting, defeat consequences, and a bind/release
lifecycle; a parallel Mount model would duplicate all of that for no mechanical gain,
and `CompanionArchetype.is_mount` already existed as a dormant descriptive tag (#1863)
specifically anticipating this reuse. (2) **A blanket mounted stat bonus** (e.g. flat
combat bonuses for simply being mounted) — rejected because it would reward the state
itself rather than the deliberate maneuvers (charge, joust) a rider chooses to commit
to; Mounted stays a pure gate, all mechanical payoff lives on CHARGE/JOUST. (3) **A
bespoke joust engine** (its own check pipeline, its own damage function) — rejected in
favor of reusing `CombatTechniqueResolver._roll_check` (so EFFORT/PULL/bond bonuses and
the LANCE_UNMOUNTED_PENALTY gate compose identically to a normal attack) and the
existing mirror-`CombatOpponent` duel-damage path (so non-lethal PvP capping isn't
reimplemented) — a joust is "two normal attack checks, compared," not a new pipeline.

> Status: accepted · Source: issue #1843 · Confidence: built & tested
> (`world/companions/tests/test_mount_state.py`, `world/combat/tests/test_mounted_combat.py`,
> Postgres tier); mount lifecycle in `world/companions/services.py` +
> `world/companions/mount_content.py`; CHARGE/JOUST in `world/combat/services.py`
> (`declare_charge`/`declare_joust`/`_resolve_charge_movement`/`_resolve_joust_pass`).
