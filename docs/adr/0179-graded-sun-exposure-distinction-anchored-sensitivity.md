# ADR-0179: Graded felt sun exposure; sensitivity is distinction-anchored, tag-identified

**Status:** Accepted (built #2846; extends ADR-0073)

**Decision.** Sunlight vulnerability is one non-negative number per character per room —
`felt_sun_exposure` = base(IC phase × sky exposure) − graded shade (the #1744/#1756
radiant-shelter cascade read as a value, not a boolean) − clothing coverage
(`ItemTemplate.is_revealing` walk + authored `GarmentMitigation` SUN rows, resonance-imbued
tracked separately) − `sun_mitigation` modifier magic — mapped to condition severity by the
character's sensitivity tier. The tier is anchored on **held Distinctions** (`Bane: Sunlight` /
`Allergy: Sunlight`), identified by `DistinctionTag` (`sun-bane`/`sun-allergy`, the #2752
pattern), never by species probe or name string: species stamp them innately via
`SpeciesGiftGrant.drawback_distinction`, any other species may take one voluntarily in CG for
reimbursement (negative `cost_per_rank`), and both resolve identically. Severity drives
`ConditionStage` thresholds — low stages impair (severity-scaled check penalties), only
Burning+ carries stage-level fixed radiant DoT — so mitigation moves you along one continuum
instead of toggling a gate. The AFK layer is hazard-generic: `HazardResponseState` prompts once
on entering a damaging stage (web + telnet), and auto-flees to the nearest shade-safe,
preferably non-public room only after a second unanswered damage instance; the ADR-0049
abandonment pool is unchanged as the floor. Bane keeps a severity floor that only real shadow
clears — clothing and magic stop the damage, never the debuff.

**Rejected alternatives.** (a) A `sun_sensitivity` field on `SpeciesGiftGrant` — couldn't serve
the voluntary path and duplicated what the stamped distinction already carries. (b) A
severity-scaled single DoT on the template — multiplication made high severities
instantaneously lethal and gave no damage-free-but-debuffed band; stage-level fixed damage
gates both by threshold. (c) A generic hazard engine app — ADR-0073 already rejected bespoke
environmental machinery; only the response-prompt layer is generic because the moon arc
(#2845) genuinely reuses it. (d) Coverage as a percentage model — the worn-slot walk plus a
revealing flag expresses "dressed at all matters, purpose-made gear goes further" with zero new
wardrobe schema.
