# ADR-5091: Stats, skills and threads read on one scale, the stored value

Stats were stored at ten times the number a player saw (strength 2 stored as 20) and every
stat surface divided by 10 (ADR-0193), threads did the same (#4585: crossings, unlocks and
pull-effect minimums authored on a "shown" level of `level // 10`), while skills showed
their stored value. Two scales on one sheet made every new feature carry conversions at its
edges, and a raw level compared against a shown-scale number was an easy bug to write. We
decided every surface (web, telnet, admin, narration, character creation) shows a stat, a
skill or a thread at its stored value: a stat of 20 reads 20, a thread at 30 reads 30. Storage
did not change; instead every authored or config number written in the old shown unit was
restated in stored units (data migration `0399_one_scale_values`, code constants in place), so
every gate fires exactly where it did: band caps 5/6/11/16/21/25 became 50/60/110/160/210/250,
crossings 3/6/11/16/21 became thread levels 30/60/110/160/210, CG allocates stats 10 to 50 in
steps of 10, vow focus picks sit at levels 10/20/30. `display_trait_value`,
`STAT_DISPLAY_DIVISOR`, `shown_thread_level` and the skill "3.0" divisor are gone; a stat
point is `STAT_POINT_VALUE` (10), the step CG allocation, maturation, level stat points and GM
raises move a stat by. We rejected the other unification, declaring the small numbers the
stored scale, because checks, modifiers, development and point conversion all already run on
the fine-grained values.

Formulas that were tuned per shown level (soul tether caps, the Hollow's size, facet effect
bonuses, vow added-effect scaling, vow stat scaling on a maneuver effect, derived amounts with
a thread-level input, the outfit trickle, a vow's size step, fatigue capacity) keep their exact
numbers through one deliberate internal step: `thread_rung(level)` (`level // 10`,
`world.magic.services.threads`) for threads and `whole_stat_points(value)` for stats. That
step is never shown, and staff help text reads "per 10 thread levels". We rejected restating
those multipliers per stored level (2 per shown level to 0.2 per stored level): it needs
fractional columns, and a thread at 35 would start counting its extra 5, which changes
gameplay.

**Consequences.** Numbers players and staff see got ten times bigger for stats and threads;
nothing a character can do changed. The rung is one helper so that a later rethink, in which
per-level formulas feed aggregate point totals that a tier curve turns into tiers (diminishing
returns from the curve), can replace it in one place; that rethink is out of scope here and
added no per-level multipliers. Content-repo fixtures exported before this change carry the
old values and the old `NPCPresetTraitLine.display_value` name; the database is the master
copy (ADR-0238), so they are re-exported, never loaded back.

> Status: accepted · Source: issue #5091; maintainer direction 2026-11-12 ("stats/skills/threads should all read the same", threads mirror skills); supersedes ADR-0193 and the shown-level rule of #4585
