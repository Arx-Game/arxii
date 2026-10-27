"""Monotonic validation for surge degree bands (#4737).

A better roll outcome must never give a lower beneficial number. For a surge band that
means a better outcome has intensity and control change at least as large as a worse
outcome's, and may not carry a condition (a debuff) where a worse outcome carries none.
Equal rows are fine. The model's ``clean()``, the admin inline and the stored-content
check all call ``validate_surge_bands`` so there is one rule.
"""

from collections.abc import Sequence
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import SurgeDegreeBand


def _outcome_label(band: "SurgeDegreeBand") -> str:
    return band.outcome.name


def validate_surge_bands(bands: Sequence["SurgeDegreeBand"]) -> list[str]:
    """Return a problem line for every adjacent pair of bands that breaks the rule.

    Bands are sorted by ``outcome.success_level`` and each is compared with the next
    better one, so a single bad row produces a single line.
    """
    ordered = sorted(bands, key=lambda band: band.outcome.success_level)
    problems: list[str] = []
    for worse, better in pairwise(ordered):
        if worse.outcome.success_level == better.outcome.success_level:
            continue
        pair = f"'{_outcome_label(better)}' is a better outcome than '{_outcome_label(worse)}'"
        if better.intensity < worse.intensity:
            problems.append(f"{pair}, so its intensity cannot be lower ({better.intensity}).")
        if better.control_change < worse.control_change:
            problems.append(f"{pair}, so its control change cannot be lower.")
        if better.condition_id is not None and worse.condition_id is None:
            problems.append(f"{pair}, so it cannot carry a condition the worse outcome lacks.")
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
