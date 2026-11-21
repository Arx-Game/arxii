"""The read-only odds and cost tables on the Divine Intervention Config page (#4349).

Both are computed from the current settings and never listed in code: the odds from the same
result charts a roll uses, the cost from the award rows in Devotion config with the favor
softening applied. Each odds row is an example character whose inputs are stated beside it, so
a number can be traced to the favor, invocation modifier and difficulty that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.scenes.action_constants import DIFFICULTY_VALUES, MIN_DIFFICULTY_POINTS
from world.worship.constants import FavorAwardKind

if TYPE_CHECKING:
    from world.worship.models import DevotionConfig

#: The favor invocation modifier the example faith niche holds (spec section 4, example value).
EXAMPLE_FAVOR_MODIFIER = 30

#: What each result is called on the tables, by its success level.
RESULT_WORDS: dict[int, str] = {
    -2: "Backfire",
    -1: "Unanswered",
    0: "Lesser answer",
    1: "Rescue",
    2: "Bigger miracle",
}


@dataclass(frozen=True)
class OddsRow:
    """One example character's chance of each result, with the inputs that set it."""

    archetype: str
    inputs: str
    difficulty: int
    percents: dict[int, int]


@dataclass(frozen=True)
class CostRow:
    """What one result costs: favor spent, and the owed favor and wait for each favor band."""

    result: str
    spent: int
    owed: tuple[int, int, int]
    wait_hours: tuple[int, int, int]


def _favor_ease(favor: int, config: DevotionConfig) -> int:
    if favor >= config.favor_ease_high_threshold:
        return config.favor_ease_high_points
    if favor >= config.favor_ease_low_threshold:
        return config.favor_ease_low_points
    return 0


def _band_words(points: int) -> str:
    from world.worship.invocation_services import band_for_points  # noqa: PLC0415

    return f"{band_for_points(points).title()} {points}"


def _example(  # noqa: PLR0913 - one example character's inputs
    *,
    archetype: str,
    favor: int,
    modifier: int,
    immune: bool,
    config: DevotionConfig,
    roller: int,
) -> OddsRow | None:
    from world.worship.sacrifice_services import sacrifice_odds  # noqa: PLC0415

    ease = _favor_ease(favor, config)
    base = DIFFICULTY_VALUES[config.base_difficulty]
    difficulty = max(base - ease - modifier, MIN_DIFFICULTY_POINTS)
    odds = sacrifice_odds(difficulty, roller_points=roller)
    if odds is None:
        return None
    percents: dict[int, int] = {}
    for line in odds.lines:
        level = max(min(line.success_level, 2), -2)
        percents[level] = percents.get(level, 0) + line.percent
    if immune:
        # Botch immunity caps a botch at a Failure: its chance moves to Unanswered.
        percents[-1] = percents.get(-1, 0) + percents.pop(-2, 0)
    inputs = (
        f"favor {favor} (ease {ease}), favor invocation modifier +{modifier}, "
        f"{_band_words(difficulty)}" + (", botch immune" if immune else "")
    )
    return OddsRow(archetype=archetype, inputs=inputs, difficulty=difficulty, percents=percents)


def odds_rows() -> list[OddsRow]:
    """The four example characters of the spec, for the reference roller in Devotion config.

    A faith niche at high favor (a +30 favor invocation modifier and botch immunity), high
    favor without the niche, a low-favor outsider at the prayer gate, and an estranged Chosen
    (the Chosen distinction's modifier, no botch immunity). Favor is read from the configured
    bands: the high band's threshold plus 5, and the prayer gate capped below the low band.
    """
    from world.mechanics.constants import FAVOR_INVOCATION_CATEGORY_NAME  # noqa: PLC0415
    from world.worship.favor_services import chosen_distinction_patron_value  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415
    from world.worship.services import get_divine_intervention_config  # noqa: PLC0415

    config = get_devotion_config()
    gate = get_divine_intervention_config().prayer_favor_gate
    high = config.favor_ease_high_threshold + 5
    outsider = min(gate, config.favor_ease_low_threshold - 1)
    chosen = chosen_distinction_patron_value(FAVOR_INVOCATION_CATEGORY_NAME)
    roller = config.odds_reference_roller_points
    examples = (
        ("Faith niche, high favor", high, EXAMPLE_FAVOR_MODIFIER, True),
        ("High favor, no niche", high, 0, False),
        ("Low-favor outsider", outsider, 0, False),
        ("Estranged Chosen", outsider, chosen or EXAMPLE_FAVOR_MODIFIER, False),
    )
    rows = [
        _example(
            archetype=name,
            favor=favor,
            modifier=modifier,
            immune=immune,
            config=config,
            roller=roller,
        )
        for name, favor, modifier, immune in examples
    ]
    return [row for row in rows if row is not None]


def cost_rows() -> list[CostRow]:
    """Spend, owed favor and wait for each of the five results, from the award rows.

    Favor is spent only on a rescue or a bigger miracle. The owed favor and a wait row are
    softened at the low and high favor bands, rounded up; a result with no wait row waits the
    config's cooldown hours, unsoftened. A missing row pays 0.
    """
    from world.traits.constants import CANONICAL_OUTCOME_LEVELS  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415
    from world.worship.intervention_services import soften  # noqa: PLC0415
    from world.worship.invocation_services import (  # noqa: PLC0415
        outcome_award,
    )
    from world.worship.services import get_divine_intervention_config  # noqa: PLC0415

    cfg = get_divine_intervention_config()
    percents = (0, cfg.debt_softening_low_percent, cfg.debt_softening_high_percent)
    outcomes = {o.name: o for o in CheckOutcome.objects.filter(name__in=CANONICAL_OUTCOME_LEVELS)}
    rows = []
    for name in sorted(outcomes, key=lambda n: -outcomes[n].success_level):
        outcome = outcomes[name]
        spends = outcome.success_level >= 1
        spent = (outcome_award(FavorAwardKind.INTERVENTION_SPEND, outcome) or 0) if spends else 0
        debt = outcome_award(FavorAwardKind.INTERVENTION_DEBT, outcome) or 0
        wait = outcome_award(FavorAwardKind.INTERVENTION_WAIT_HOURS, outcome)
        rows.append(
            CostRow(
                result=name,
                spent=spent,
                owed=tuple(soften(debt, p) for p in percents),
                wait_hours=tuple(
                    soften(wait, p) if wait is not None else cfg.cooldown_hours for p in percents
                ),
            )
        )
    return rows
