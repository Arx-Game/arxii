# ADR-4601-A: Checks slide by band position, and hopeless checks are pinned on own standing

**Date:** 2026-10-23
**Status:** Accepted (spec approved on #4551)
**Issue:** #4601 (slice (b) of #4551). Builds on ADR-4593-A (charts -7 and -8) and keeps
#2707's chip charts.

## Decision

A check no longer reads only the whole rank difference. Each total has a **band position**
(how far it is through its `CheckRank` band), so the difference is fractional: whole part
`lo`, share `f`. The roll uses chart `lo` **slid** `f` of the way toward chart `lo + 1`:
each "at least X" chance of chart `lo`'s own outcomes moves in a straight line toward chart
`lo + 1`'s, and an outcome chart `lo + 1` has that chart `lo` lacks counts as chart `lo`'s
nearest outcome by success level (the lower one on a tie). No outcome a chart lacks appears
until the total reaches the next rank. There is still one roll: a d100 face (rollmod added
and clamped as before) plus a fraction inside the face, so at 0% slide every face lands
exactly where it always did. A difference below the lowest chart sits at 0% of it; one at
or above the highest chart uses that chart unslid. The code is `world/checks/slide.py`;
`perform_check` and the tuning dashboard both use it.

**The hopeless pin.** Own standing is each side's total without modifiers (#4551 decision
7: effort, fatigue, strain and soulfray are own standing; conditions, equipment,
distinctions, scene, fashion, relationships, favor and caller bonuses are modifiers, and so
are the defender's conditions inside `level_opposition`). When own standing lands on a
chart with no outcome above success level 0 (the same test as
`chart_has_success_outcomes`), the roll stays on that chart and modifiers only slide it, up
to 100% of its band. Net penalties still resolve normally onto a lower chart. The preview
grade reads the pinned chart, so a buff never changes an Impossible label. Outcome
guarantees (tier floors, botch immunity) are capped at the chart's best outcome instead of
falling back to the global outcome table.

## Why

The owner's rulings on #4551: "if you're at 75% of the way to the next tier, your chart is
75% of the way to the next chart"; "everything shifts to the right to make better outcomes
more likely, worse outcomes (on the left) less likely"; "we don't want to expose outcomes
that aren't on the charts: that's what the other charts are for"; and "our impossible charts
for situations players can't win don't suddenly become winnable through a buff". The slide
removes the dead zones (points that did not cross a threshold did nothing) with no new
tuning rows, because it reads the authored charts. Without the pin, a level-1 character
seven ranks below a foe, buffed by a crowd, won about 14% of the time.

## Rejected

- **A straight blend of the two charts' bands.** It leaks the next chart's outcomes into
  the band (1% to 4% Critical Success inside the -1 band), which the owner ruled out.
- **A second roll at the next chart with probability `f`** (how Arx 1 handled progress
  toward the next tier). Same average odds, but the owner disliked the visible jump and
  second roll.
- **Rounding the slid band edges to whole d100 faces.** Small modifiers would again do
  nothing until they crossed a face; the fraction inside the face keeps every point
  counting while leaving unslid charts face for face.
- **Pinning against penalties too.** The pin exists to stop modifiers lifting a hopeless
  check; holding a debuffed check up on its own chart would make debuffs useless exactly
  where a GM set a far-above threat.
- **A cap on total buff value.** It would also cap the sworn buffer (#4551 section 3).

## Consequences

`CheckResult.rank_difference` is the whole difference of the chart the roll used, which can
be one lower than the old whole-rank subtraction (Expert at 10% against Expert at 90% is
-0.8: chart -1 slid 20%). `CheckResult.standing` carries both sides' band positions, the
slid chart and the pin. A chart whose authored bands do not cover 1 to 100 is read as its
bands' shares of the whole roll. Callers that fold own-standing terms into
`extra_modifiers` (the social scene path folds fatigue there) or modifiers into
`target_difficulty` (the `level_opposition` callers outside combat and standoffs) count
them on the wrong side of the pin; the combat, consider and standoff read paths pass
`target_modifiers`, and gathered fatigue, strain and soulfray contributions pass as
`extra_standing`.
