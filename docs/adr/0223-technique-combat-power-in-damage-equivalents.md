# ADR-0223: Technique combat power is measured in damage-equivalents against a reference matchup, with parsed (not probed) mitigation

**Status:** Accepted (2026-08-20, #3279)

**Decision.** The tuning instrument for technique balance values every technique payload
in one currency: expected damage-equivalent (DE) per cast, an expectation over the SL
distribution of a reference matchup. Non-damage effects convert via a reference frame:
buffs = priced percent x reference outgoing DPR x expected duration; hard control =
enemy rounds denied x incoming DPR; mitigation = parsed reduction x incoming DPR x
duration; healing = damage undone, capped. Reference DPR is self-anchoring (the median
baseline attack DE of the authored corpus at the chosen context), never a hand-tuned
constant. Covenant-role amplification is reported as a second number per technique
(fully-matched anchor at a chosen thread level) computed by the same pure helpers the
live covenant power terms call, so the instrument cannot drift from combat. Mitigation
magnitudes are extracted by parsing MODIFY_PAYLOAD reactive-trigger flow steps
(`protective_magnitude`), not by an empirical run of the damage pipeline; every
valuation carries a provenance flag and unparseable shapes surface as UNPRICEABLE
authoring gaps rather than silent zeros.

**Why.** Techniques were tuned blind: `price_design` budgets inputs (intensity, authored
base damage), not outcomes, and nothing compared "18 expected damage" against "+30% team
damage for 3 rounds" or "x0.5 incoming for 2 rounds". A single contestable exchange rate,
stated openly and computed from live formulas, beats per-category metrics nobody can
trade off. Self-anchoring DPR re-anchors buff/mitigation values automatically as the
attack corpus is retuned.

**Rejected alternatives.** (a) Per-category scores with no conversion: never answers "is
this buff overpowered". (b) Sim-derived marginal win-rate value: truthful but slow,
noisy, unexplainable, and requires simulated parties to cast techniques first. (c) An
empirical mitigation probe (apply condition to a scratch target, run
`apply_damage_to_participant` with/without): the most drift-proof option and the original
recommendation, but it demands a no-DB-writes, no-idmapper-pollution harness around the
damage pipeline; ruled heavier than the need (Tehom, 2026-08-20: best guesses fine).
Parsing covers all shipped defensive content (Defend's multiply-0.5 is a regression
test); the provenance system leaves a clean seam to add a probe if trigger shapes
proliferate beyond the parser.

**Consequences.** Phase 2 (outcome-denominated authoring budgets) and phase 3
(simulation that casts techniques) consume the same evaluator. Enhancement techniques
(`enhances_effect_type`, whole runtime payload = flat +2 power) will visibly value near
zero: that is the instrument reporting a design gap, not a bug to paper over.
