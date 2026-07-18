# Technique capability folding is max-not-sum, and prerequisite-free grants only

When the one-oracle merge (#2504) folded `TechniqueCapabilityGrant` into `get_effective_capability_value`/
`get_all_capability_values` (`world.conditions.services`) so the agency/requirement oracle honors known
techniques the same way it honors an innate baseline or a condition, two shapes needed a deliberate call.
First, when a character knows several techniques that grant the same `CapabilityType`, the fold takes the
**best (max)** grant, not the sum — summing would let stacking unrelated techniques inflate one capability
past what any single technique intends, homogenizing power in a way ADR-0034 (mechanics individualize
characters) already rejects; the fold must preserve which technique is doing the work, not launder many
into one bigger number. Second, only **prerequisite-free** grants (`TechniqueCapabilityGrant.prerequisite
is None`) fold into the agency oracle — a source-level prerequisite is target-contextual (it describes when
the grant applies to a specific target/situation), so it stays availability-only
(`get_capability_sources_for_character`, `world.mechanics.services`) rather than leaking into a
context-free "can this character do X" answer. Rejected: sum-across-techniques (inflation, breaks
individuation); a possession-floor-of-1 for any known grant regardless of `calculate_value()` (flattens the
technique's actual magnitude to a boolean "has it / doesn't," which the don't-flatten-magnitude-to-boolean
principle rules out).

> Status: accepted · Source: #2504 · Related: ADR-0034 (individuation)
