# Cast-time capability effects ride the condition channel; grant tables mean standing possession

Ruled by Tehom 2026-08-29 (#3449, closing the question the 2026-08-29 combat/magic audit
filed). A `TechniqueCapabilityGrant` means exactly one thing: **standing possession** —
knowing the technique gives the character the capability, read by both oracles
(`get_effective_capability_value` folds prerequisite-free grants with real effective power;
`get_capability_sources_for_character` enumerates all grants for availability). A cast
deliberately does nothing extra with its grants, and no bespoke cast-time grant seam will be
built.

**Why:** the capability-boost-on-cast intent already has a complete, outcome-scaled delivery
channel — an applied condition carrying a `ConditionCapabilityEffect`.
`TechniqueAppliedCondition.compute_severity(effective_power, success_level)` scales the
condition with the cast's outcome, and `scales_with_severity` has been honored by every
capability reader since #2708. A second, grant-table-based cast seam would be a parallel
implementation of the same user goal (the anti-reinvention failure mode), with its own
success-level leg to invent and its own read-path to maintain.

**Consequence — the three inert payload families are stripped, not wired.**
`SignatureMotifBonusCapabilityGrant`, `AudereMajoraFaithVariantCapabilityGrant`, and
`MiracleCapabilityGrant` were each born documented "INERT until a capability-read-path issue
is built"; this ruling is that issue, and the answer is that no read path comes. Each family
keeps its applied-condition sibling (`SignatureMotifBonusAppliedCondition` via
`apply_signature_bonus_conditions`; `AudereMajoraFaithVariantAppliedCondition` applied at
crossing; `MiracleAppliedCondition`), which is where a capability-flavored effect is authored
from now on. The DE evaluator keeps pricing `TechniqueCapabilityGrant` 0 as cast-DE
(`INERT_PAYLOAD`) because its value is possession-side, priced by `capability_power_eval`.

**Rejected alternative:** a first-class cast seam in `use_technique` where a cast's outcome
modulates the caster's granted capability magnitude for a window. Rejected as redundant with
the condition channel above; if a future design wants exactly that shape, author it as a
self-targeted applied condition on the technique.

**Data disposition (ADR-0237):** the migration deletes three authored-content tables under
the *empty in production* claim — all three were inert from birth with admin help text
saying so — confirmed against prod at PR review rather than assumed.
