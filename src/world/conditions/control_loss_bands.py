"""Monotonic validation for compulsion resist bands and control-loss bands (#4802).

A better roll outcome must never be worse for the character. Bands are sorted by
``outcome.success_level``; each band is compared with the best values seen at strictly
lower success levels (outcomes sharing a level are not compared with each other), the
same way ``world.combat.surge_bands.validate_surge_bands`` does it. The model ``clean()``
methods and the admin formsets call these, so there is one rule.
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from world.conditions.constants import CompulsionResult

if TYPE_CHECKING:
    from world.conditions.models import CompulsionResistBand, ControlLossBand

# Result order, best first: a better outcome may not have a later-ranked result.
RESULT_RANK: dict[str, int] = {
    CompulsionResult.ACTS_FREELY: 0,
    CompulsionResult.ACTS_STRAINED: 1,
    CompulsionResult.COMPULSION_ACTS: 2,
}

# (label, key) where a better outcome's key must be <= the lowest key of any worse outcome
_Rule = tuple[str, Callable[[Any], int]]


def _check(bands: Sequence[Any], *, lower_is_better: Sequence[_Rule]) -> list[str]:
    """One problem line per band and rule that breaks monotonic order.

    Each rule key is a cost: a better outcome's key may not exceed the smallest key among
    strictly worse outcomes. A benefit is passed as its negation.
    """
    ordered = sorted(bands, key=lambda band: band.outcome.success_level)
    problems: list[str] = []
    seen: list[Any] = []  # bands at strictly lower success levels
    index = 0
    while index < len(ordered):
        level = ordered[index].outcome.success_level
        tier = [band for band in ordered[index:] if band.outcome.success_level == level]
        index += len(tier)
        for band in tier:
            for label, key in lower_is_better:
                if not seen:
                    continue
                floor = min(seen, key=key)
                if key(band) > key(floor):
                    problems.append(
                        f"'{band.outcome.name}' is a better outcome than "
                        f"'{floor.outcome.name}', so its {label} cannot be worse."
                    )
        seen.extend(tier)
    return problems


def validate_compulsion_bands(bands: Sequence["CompulsionResistBand"]) -> list[str]:
    """Problem lines for resist bands where a better outcome is worse for the character.

    Result order is ACTS_FREELY > ACTS_STRAINED > COMPULSION_ACTS. A better outcome may
    not have a worse result, a bigger ``action_penalty`` or a lower ``control_change``.
    """
    return _check(
        bands,
        lower_is_better=[
            ("result", lambda band: RESULT_RANK[band.result]),
            ("action penalty", lambda band: band.action_penalty),
            ("control change", lambda band: -band.control_change),
        ],
    )


def validate_control_loss_bands(bands: Sequence["ControlLossBand"]) -> list[str]:
    """Problem lines for control-loss bands that break order or trade control badly.

    Monotonic order: a better outcome may not have a lower ``control_change``, or a higher
    ``severity`` or ``duration_rounds``. ``intensity`` is left out of the order on purpose:
    losing control trades control for power, so a worse roll may well raise intensity (the
    approved #4802 demo's wound trigger gives +4 on a Failure and +5 on a Critical Failure).

    The trade itself is checked band by band (ruled 2026-11-01, #4887): gaining control is
    never a negative, and a failure loses more than it gains. See ``_trade_problems``.
    """
    problems = _check(
        bands,
        lower_is_better=[
            ("control change", lambda band: -band.control_change),
            ("severity", lambda band: band.severity),
            ("duration", lambda band: band.duration_rounds),
        ],
    )
    for band in sorted(bands, key=lambda band: band.outcome.success_level):
        problems.extend(_trade_problems(band))
    return problems


def _trade_problems(band: "ControlLossBand") -> list[str]:
    """The control-for-power trade rules for one band.

    A successful band (success level above 0) may not lower Control. It cannot lower
    Intensity either, since ``intensity`` only ever adds. A failed band (success level
    below 0) may not add more Intensity than the Control it takes away. A band at level 0
    is neither, and is checked by the monotonic order only.
    """
    level = band.outcome.success_level
    name = band.outcome.name
    if level > 0 and band.control_change < 0:
        return [
            f"'{name}' is a success, so it cannot lower Control "
            f"(it has Control {band.control_change:+d})."
        ]
    if level < 0 and band.intensity > -band.control_change:
        return [
            f"'{name}' is a failure, so it cannot add more Intensity than the Control it "
            f"takes away (it has Intensity +{band.intensity}, "
            f"Control {band.control_change:+d})."
        ]
    return []
