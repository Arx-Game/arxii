# `rank_difference` is roller minus target; positive means the roller is stronger and gets the easier chart

#2707 (level both sides of check) started as a level-scaling change and immediately hit
a structural bug underneath it: adding level points to an inverted result-chart ladder
would have made higher-level characters roll *worse*, and the test fallout would have
been uninterpretable. Fixing the inversion first, and recording the convention it
restores, is this ADR.

## Decision

**`rank_difference = roller_rank - target_rank`, and positive means the roller is
stronger and gets the easier chart.** This is not a new rule — it is what
`ResultChart.rank_difference`'s own `help_text` already stated and what
`_compute_check_breakdown` already computed (`rank_difference = roller_rank.rank -
target_rank.rank`). The bug was entirely in the seeded chart *content*: the bands
attached to each `rank_difference` value had the difficulty gradient backwards, so a
positive (roller-favored) difference resolved against a *harder* chart than a negative
(target-favored) one — the exact inverse of what the field's own documentation
promised.

**The inversion was measured, not assumed.** Before the fix, an Expert-ranked roller
against a Trivial-difficulty target (a strongly roller-favored `rank_difference`)
succeeded only 15% of the time, while an Incompetent-ranked roller against an
Expert-level difficulty (a strongly target-favored `rank_difference`) succeeded 80% of
the time — precisely backwards from what any check-resolution system should produce.

**Nothing asserted direction for the life of the project.** No test anywhere checked
that a stronger roller actually got an easier outcome distribution than a weaker one;
every existing test either fixed a specific `rank_difference` and asserted its own
(equally inverted) expectation, or forced the outcome outright. The bug was invisible to
the suite because the suite never encoded the relationship the field's `help_text`
promised — only the raw lookup, which was internally consistent with itself just
backwards relative to intent.

**`world/checks/tests/test_chart_direction.py` is now the guard.** It asserts the
*directional* property directly — a stronger roller's success rate must exceed a weaker
roller's, across the full seeded `rank_difference` range — rather than pinning any one
chart's exact bands, so a future re-seed of the content can't silently reintroduce the
inversion the way the original seed did.

## Rejected alternatives

- **Negate `rank_difference` in the engine, so a chart's name reads as "difficulty"
  instead of "roller advantage"** — flip the sign in `_compute_check_breakdown` and
  reinterpret the seeded chart keys to mean "how hard this is for the roller," rather
  than fixing which bands are attached to which sign. Rejected: `ResultChart
  .rank_difference`'s own `help_text` already defines the field as roller-relative and
  positive-favors-roller — the field's documentation is authoritative, and it agrees
  with what the engine already computed. The seeded *content* was the thing out of step
  with the documented contract, not the engine's arithmetic; negating the engine would
  have made the code disagree with its own field's stated meaning to work around a
  content bug.

## Facts for future readers

- This fix necessarily precedes #2707's level-points work (ADR-0164): level points add
  onto `total_points`, which feeds `rank_difference` — adding a floor on top of an
  inverted ladder would have made a higher-level character's guaranteed level points
  actively hurt them.

> Status: accepted · Source: issue #2707 (level both sides of check) · relates to
> ADR-0164 (level as a two-sided check term; landed alongside this); extends ADR-0019;
> supersedes nothing.
