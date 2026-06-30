# Gift strength comes from the thread woven into it (the costliest thread kind)

A character grows stronger in a gift — unlocking more, and more-powerful, techniques — through the
**thread woven into that gift**, so you deepen a species or minor gift by investing its thread; and
because that gift-thread fundamentally gates a character's magical power, it is the **most expensive
thread kind** to raise. We rejected level-driven gift power: ADR-0046 keeps tier *breakthroughs* as
fixed-threshold drama while thread depth is the continuous within-tier strength axis — tying power to
a woven thread keeps magical strength earned through invested RP rather than handed out by leveling.
Today threads cannot target a `Gift` (the `TargetKind` set has no GIFT) and thread cost varies by
tier/level/path but never by target kind, so both the gift anchor and the per-kind cost are new build. This gift-thread is the gift-side
instance of the shared specialization engine (ADR-0055): at thread level 3 the gift grants techniques
customized to the character's specific resonance, in parity with covenant sub-roles. The gift-thread is the *primary* power axis; an optional
per-technique "signature" thread adds depth to a single technique above this baseline (ADR-0056).

**Clarification (#1581):** the "costliest thread kind" premium applies to **imbuing/raising** a
gift-thread (`ThreadPullCost.imbue_cost_multiplier`), not to **pulling/using** it. We rejected a
per-target-kind *pull*-cost axis (it would penalize a character at point of use for being stronger /
for having imbued — a mixed blessing): pull cost stays uniform across kinds.

**Strict bonus (#1581 Task 7):** a gift-technique variant is **always a bonus, never a penalty**.
When the variant's anima cost (driven by its `intensity_delta`) would exceed the base form's
cost, `use_technique` clamps `cost = min(variant_cost, base_form_cost)`. We rejected letting a
variant raise anima cost — "never punish achievement": the reward for imbuing a GIFT thread is
strictly non-negative at point of use. Implemented via two `get_runtime_technique_stats` calls
(once with `apply_variant=True`, once with `apply_variant=False`) and a `min()` clamp.

**Base form opt-out (#1581 Task 8):** the variant is the **default** at cast time, but a player may
cast the base form when the resonance-tied variant character is situationally unwanted. Surface:
`request_technique_cast(..., use_base_form=True)` bypasses variant resolution; telnet `cast
<technique> base` keyword; web cast payload field `use_base_form`. Combat opt-out and a React
toggle are follow-ups. `use_technique(apply_variant=False)` propagates the opt-out through the
anima-cost and power-ledger paths.

> Status: accepted · Source: design discussion 2026-06-27 · Built: #1578 (GIFT thread anchor +
> specialization engine); #1580 (anchor cap + always-in-action); #1581 (cast-time variant resolution +
> imbue premium via `imbue_cost_multiplier`; per-target-kind pull cost rejected — pull stays uniform;
> strict-bonus clamp + base opt-out)
