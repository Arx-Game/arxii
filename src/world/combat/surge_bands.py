"""Monotonic validation for surge degree bands (#4737).

A better roll outcome must never give a lower beneficial number. For a surge band that
means a better outcome has intensity and control change at least as large as a worse
outcome's, and may not carry a condition (a debuff) where a worse outcome carries none.
Equal rows are fine. The model's ``clean()``, the admin inline and the stored-content
check all call ``validate_surge_bands`` so there is one rule.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import SurgeDegreeBand


def _pair(better: "SurgeDegreeBand", worse: "SurgeDegreeBand") -> str:
    return f"'{better.outcome.name}' is a better outcome than '{worse.outcome.name}'"


def validate_surge_bands(bands: Sequence["SurgeDegreeBand"]) -> list[str]:
    """Return a problem line for every band that is worse than a strictly worse outcome.

    Bands are sorted by ``outcome.success_level``. Each band is compared with the best
    values seen at strictly lower success levels (several outcomes can share a level, and
    those are not compared with each other), so one bad row produces one line per field.
    """
    ordered = sorted(bands, key=lambda band: band.outcome.success_level)
    problems: list[str] = []
    top_intensity: SurgeDegreeBand | None = None
    top_control: SurgeDegreeBand | None = None
    bare: SurgeDegreeBand | None = None  # a lower band with no condition
    index = 0
    while index < len(ordered):
        level = ordered[index].outcome.success_level
        tier = [band for band in ordered[index:] if band.outcome.success_level == level]
        index += len(tier)
        for band in tier:
            if top_intensity is not None and band.intensity < top_intensity.intensity:
                problems.append(
                    f"{_pair(band, top_intensity)}, so its intensity cannot be lower "
                    f"({band.intensity})."
                )
            if top_control is not None and band.control_change < top_control.control_change:
                problems.append(
                    f"{_pair(band, top_control)}, so its control change cannot be lower."
                )
            if band.condition_id is not None and bare is not None:
                problems.append(
                    f"{_pair(band, bare)}, so it cannot carry a condition the worse outcome lacks."
                )
        for band in tier:
            if top_intensity is None or band.intensity > top_intensity.intensity:
                top_intensity = band
            if top_control is None or band.control_change > top_control.control_change:
                top_control = band
            if bare is None and band.condition_id is None:
                bare = band
    return problems


def check_stored_surge_bands() -> list[str]:
    """Run ``validate_surge_bands`` over every stored ``SurgeTuning``; return the problems."""
    from world.combat.models import SurgeDegreeBand  # noqa: PLC0415

    by_tuning: dict[int, list[SurgeDegreeBand]] = {}
    for band in SurgeDegreeBand.objects.select_related("tuning", "outcome"):
        by_tuning.setdefault(band.tuning_id, []).append(band)
    problems: list[str] = []
    for bands in by_tuning.values():
        label = bands[0].tuning.get_trigger_kind_display()
        problems.extend(f"{label}: {line}" for line in validate_surge_bands(bands))
    return problems
