# Capabilities reach checks only through authored CheckTypeCapabilityModifier rows

Before #2505, a character's capability values (technique grants, trait derivations, condition
boosts — collected via `get_effective_capability_value`, the agency oracle) had no path into
`perform_check`'s point total at all: the availability oracle (`get_capability_sources_for_character`)
fed challenge-approach eligibility, but nothing folded a capability's raw value into a roll. The
fix: `CheckTypeCapabilityModifier` (`world/checks/models.py`) is a curated, staff-authored
`(check_type, capability, weight)` row — only a check type with an explicit row for a capability
ever reads it, and the contribution is `weight * effective_capability_value`, summed and truncated
toward zero once (`_capability_point_allocation`, shared by the roll path and the
`collect_check_modifiers` provenance path so the two can't drift). `resolve_challenge()`
additionally folds the acting `CapabilitySource`'s own `.value` (the specific technique/trait/
condition source that chose the approach) directly into `extra_modifiers` before calling
`perform_check` — a second, narrower channel for the one capability instance actually in play,
distinct from the general curated table. Rejected: name-based inference linking every
`CapabilityType` to every `CheckType` sharing a name or keyword — uncurated and collision-prone,
the same failure mode the project's curated-checks rule (ADR-0110) already rejects for GM-invoked
checks; and folding every capability a character holds into every check unconditionally — drowns
the authorial signal of which checks a given capability is meant to matter to, and risks
double-counting a single condition's effect when it also reaches the same check via a direct
`ConditionCheckModifier` (see `docs/systems/checks.md`'s authoring guardrail).

> Status: accepted · Source: issue #2505 · Related: ADR-0019 (unified resolution pipeline this
> extends), ADR-0110 (curated-never-invented precedent for GM-invoked checks)
