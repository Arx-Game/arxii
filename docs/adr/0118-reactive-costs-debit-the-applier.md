# Reactive ward costs debit the applier, falling back to the bearer

An ally ward (Aegis Ward/Communion, Mirror Vigil/Communion, Phase Guard/Communion, #2208) must
strain its caster, not the ally wearing it — otherwise a warded ally gets a free defense paid
for by no one. Both reactive-cost paths added in ADR-0060 (`_try_spend_reactive`, paid per fire,
and `drain_reactive_upkeep`, drained per round) now resolve the payer as
`ConditionInstance.source_character`, falling back to the bearer (`target`) when unset. Self-cast
wards are unchanged by construction: their `source_character` already equals the bearer, so the
fallback never triggers for them. An upkeep payer who can't afford the round cost causes the ward
to lapse (its `ConditionInstance` row deletes, cascading any `Trigger` rows), exactly as an
unaffordable self-ward already did. We rejected adding per-variant cost flags to
`ConditionTemplate` (e.g. a `payer_is_source` bool per template) — the payer rule is a single
invariant true of every reactive condition regardless of who cast it, not a per-template choice,
so a flag would be authored surface duplicating a rule the FK topology already encodes for free.

> Status: accepted · Source: #2208, #2040 · Confidence: built & tested (
> `world/magic/tests/test_ally_ward_costs.py`); `ConditionInstance.source_character` fallback in
> `world/magic/services/effect_handlers.py::_try_spend_reactive` and
> `world/combat/services.py::drain_reactive_upkeep`; extends ADR-0060's cost-fizzle family.
