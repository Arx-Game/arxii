# ADR-0269: Upbringings price standing as family influence times position

**Status:** Accepted (#3617, 2026-09-03, TehomCD ruling). Related ADR-0268, ADR-0209.

**Context.** The CG cost of a character's standing depends on two things: how powerful the family is and how powerful the character is within it. Running a powerless family is free; a disposable mook in a mighty house pays a token point; a middling seat in a mighty house costs about what running a moderate one does; running a very powerful family is very expensive. A flat cost per choice cannot produce that table.

**Decision.** Each `OriginTemplateSlotChoice` carries `cg_point_cost` (flat) and `cost_per_influence`; a claim-path pick costs flat + per-influence x `Family.influence`. On the name and none paths influence is 0. The Upbringing carries its own flat `cg_point_cost`. Every number is a row value staff tune in admin.

**Rejected.** A flat cost per choice (cannot express the table). House Stature (#3091, ADR-0209) as the price base: it is live and computed, moves mid-draft, and lives on the house organisation rather than the family. A cost table row per (kind x role): heavy to author and still misses per-family differences.
