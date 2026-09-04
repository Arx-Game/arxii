# ADR-0255: Consented reactions join the Soulfray ledger; flat pay-or-fizzle stays the default

**Status:** Accepted (2026-09-02) · **Issue:** #3573 · Amends ADR-0118 (guardian-reaction-seam)

ADR-0118 kept guardian reactions outside `use_technique`: a flat `reactive_anima_cost`,
pay-or-fizzle, no Soulfray ledger, because a save reacting to someone else's attack is not
a casting session. That reasoning still holds for the default. It also meant a guardian
who had run dry could never choose to save a friend anyway, and the ruling on #3573 is
that they must be able to: a conscious opt-in, never automatic, always available. So the
reaction seams (`_try_technique_interpose`, `_try_spend_reactive`, `drain_reactive_upkeep`)
now branch on consent captured in advance (`CombatRoundAction.confirm_soulfray_risk` for
a declared interpose, `ConditionInstance.soulfray_consented` stamped from the cast for
wards): unconsented is unchanged (fizzle or lapse); consented debits through
`deduct_anima` (glut-first, deficit-capable, non-lethal clamp) and accrues through the
shared `world.magic.services.soulfray.accumulate_soulfray` on every fire, deficit or
not, so a low guardian accrues the way a low caster does. The flat fee stays flat.
Rejected: routing consented reactions through `use_technique` (its cast-event fan-out
and mishap rider are wrong for a save, exactly as ADR-0118 said); scaling the reactive
fee with intensity (not ruled; a separate question); a per-fire prompt (reactions fire
inside someone else's resolution, so consent has to be captured beforehand).

> Status: accepted · Source: #3573 · Confidence: built & tested
> (`world/combat/tests/test_guardian_reactions.py`, `world/magic/tests/test_ally_ward_costs.py`,
> `world/combat/tests/test_reactive_upkeep.py`, `world/scenes/tests/test_cast_services.py`)
