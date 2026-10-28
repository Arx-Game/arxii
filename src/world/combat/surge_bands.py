"""Monotonic validation for surge degree bands (#4737).

A better roll outcome must never give a lower beneficial number. For a surge band that
means a better outcome has intensity and control change at least as large as a worse
outcome's, and may not carry a condition (a debuff) where a worse outcome carries none.
Equal rows are fine.

A condition that feeds intensity (a stage with ``intensity_per_round > 0``, an emotional
condition, #4739) is a benefit, not a cost: a better outcome may carry it where a worse one
does not, and may not drop one a worse outcome carries. Emotional conditions come only from
a success or a choice, so a band whose outcome is a failed roll (success level below 1) may
not carry one at all. The model's ``clean()``, the admin inline and the stored-content
check all call ``validate_surge_bands`` so there is one rule.
"""

from collections.abc import Collection, Sequence
from typing import TYPE_CHECKING

from world.combat.condition_surges import condition_feeds_intensity

if TYPE_CHECKING:
    from world.combat.models import SurgeDegreeBand


def _pair(better: "SurgeDegreeBand", worse: "SurgeDegreeBand") -> str:
    return f"'{better.outcome.name}' is a better outcome than '{worse.outcome.name}'"


def _condition_problems(
    band: "SurgeDegreeBand",
    feeding: set[int],
    *,
    bare: "SurgeDegreeBand | None",
    fed: "SurgeDegreeBand | None",
) -> list[str]:
    """The condition rules for one band against the lower bands already seen.

    ``bare`` is a lower band with no cost condition and ``fed`` a lower band carrying a
    feeding condition. A feeding condition is a benefit; any other condition is a cost.
    """
    feeds = band.condition_id in feeding
    problems: list[str] = []
    if feeds and band.outcome.success_level < 1:
        problems.append(
            f"'{band.outcome.name}' is a failed roll, so it cannot carry "
            f"'{band.condition.name}', which feeds intensity."
        )
    if band.condition_id is not None and not feeds and bare is not None:
        problems.append(
            f"{_pair(band, bare)}, so it cannot carry a condition the worse outcome lacks."
        )
    if fed is not None and not feeds:
        problems.append(
            f"{_pair(band, fed)}, so it cannot drop the intensity-feeding condition "
            "the worse outcome carries."
        )
    return problems


def validate_surge_bands(
    bands: Sequence["SurgeDegreeBand"],
    *,
    feeding_condition_ids: Collection[int] | None = None,
) -> list[str]:
    """Return a problem line for every band that is worse than a strictly worse outcome.

    Bands are sorted by ``outcome.success_level``. Each band is compared with the best
    values seen at strictly lower success levels (several outcomes can share a level, and
    those are not compared with each other), so one bad row produces one line per field.

    ``feeding_condition_ids`` are the band conditions that feed intensity; a caller that
    already knows them passes them, otherwise they are read in one query.
    """
    feeding = (
        condition_feeds_intensity(band.condition_id for band in bands)
        if feeding_condition_ids is None
        else set(feeding_condition_ids)
    )
    ordered = sorted(bands, key=lambda band: band.outcome.success_level)
    problems: list[str] = []
    top_intensity: SurgeDegreeBand | None = None
    top_control: SurgeDegreeBand | None = None
    bare: SurgeDegreeBand | None = None  # a lower band with no cost condition
    fed: SurgeDegreeBand | None = None  # a lower band carrying a feeding condition
    index = 0
    while index < len(ordered):
        level = ordered[index].outcome.success_level
        tier = [band for band in ordered[index:] if band.outcome.success_level == level]
        index += len(tier)
        for band in tier:
            problems.extend(_condition_problems(band, feeding, bare=bare, fed=fed))
            if top_intensity is not None and band.intensity < top_intensity.intensity:
                problems.append(
                    f"{_pair(band, top_intensity)}, so its intensity cannot be lower "
                    f"({band.intensity})."
                )
            if top_control is not None and band.control_change < top_control.control_change:
                problems.append(
                    f"{_pair(band, top_control)}, so its control change cannot be lower."
                )
        for band in tier:
            feeds = band.condition_id in feeding
            if top_intensity is None or band.intensity > top_intensity.intensity:
                top_intensity = band
            if top_control is None or band.control_change > top_control.control_change:
                top_control = band
            if bare is None and (band.condition_id is None or feeds):
                bare = band
            if fed is None and feeds:
                fed = band
    return problems


def check_stored_surge_bands() -> list[str]:
    """Run ``validate_surge_bands`` over every stored ``SurgeTuning``; return the problems."""
    from world.combat.models import SurgeDegreeBand  # noqa: PLC0415

    by_tuning: dict[int, list[SurgeDegreeBand]] = {}
    for band in SurgeDegreeBand.objects.select_related("tuning", "outcome", "condition"):
        by_tuning.setdefault(band.tuning_id, []).append(band)
    feeding = condition_feeds_intensity(
        band.condition_id for bands in by_tuning.values() for band in bands
    )
    problems: list[str] = []
    for bands in by_tuning.values():
        label = bands[0].tuning.get_trigger_kind_display()
        problems.extend(
            f"{label}: {line}"
            for line in validate_surge_bands(bands, feeding_condition_ids=feeding)
        )
    return problems
