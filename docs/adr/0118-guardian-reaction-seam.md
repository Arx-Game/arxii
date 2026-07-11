# ADR-0118: Declared guardian reactions roll the caster's cast check outside `use_technique`

**Status:** Accepted (2026-07-11) · **Issue:** #2207

A technique-guardian's protective reaction (`declare_interpose(technique=...)` →
`world.combat.services._try_technique_interpose`) rolls the guardian's own cast check
(`resolve_cast_check_type`, ADR-0096) directly via `perform_check` against the Interpose
challenge's authored severity (`ChallengeTemplate.severity`) — it never calls
`world.magic.services.techniques.use_technique`. Cost and fizzle follow the existing
reactive-defense cost family (`ConditionTemplate.reactive_anima_cost`, ADR-0060) rather
than `calculate_effective_anima_cost`: the guardian pays a flat anima cost on fire, and
an unaffordable cost fizzles silently — no roll, no charge, damage proceeds unchanged to
the next protection layer — the same shape `absorb_pool`/`reflect_damage`/`blink_dodge`
already use for standing reactive defenses, just extended to a *declared* reaction chosen
at combat-round-declaration time instead of a standing condition's trigger firing on
`DAMAGE_PRE_APPLY`. Rejected alternative: routing the guardian's reaction through
`use_technique` with a custom `resolve_fn`. `use_technique` orchestrates a live cast —
Strain/overburn-aware `calculate_effective_anima_cost`, Soulfray-risk confirmation and
accrual, and the TECHNIQUE_PRE_CAST/CAST/AFFECTED event trio — all correct for a caster
spending their own turn to cast, wrong for a guardian's out-of-turn save reacting to
someone else's attack landing on a third party. A reaction is mechanically a save: it
needs a check and a flat pay-or-fizzle cost, not a casting session's Soulfray ledger or
a cast-event fan-out into a round that isn't the guardian's own declared cast.

> Status: accepted · Source: issue #2207 · Confidence: built & tested
> (`world/combat/tests/test_guardian_reactions.py` —
> `TechniqueGuardianBarrierResolutionTest`, SQLite tier); extends ADR-0060's reactive-cost
> family to declared (not just standing-condition-triggered) reactions;
> `_try_technique_interpose` in `world/combat/services.py`.
