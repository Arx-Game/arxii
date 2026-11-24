"""The bonus resonance check (#5308).

Every earned resonance gain rolls one check per affinity it pays, and every pull and
kindled cast rolls one for its worth. The check type is ``ResonanceGainConfig.bonus_check_type``;
the act's own stat replaces its stat and the affinity's skill is added. What the result is
worth comes from the staff table ``ResonanceCheckAward``. Nothing here names a skill: the skill
is reached only through ``Affinity.skill`` (ADR-4450).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

from world.checks.models import CheckTypeTrait
from world.checks.types import ExtraTraitTerm
from world.magic.models import Affinity, ResonanceCheckAward, ResonanceGainSourceStat
from world.magic.types.resonance_checks import NO_GAIN_BONUS, GainBonus
from world.traits.constants import TraitType

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckOutcome, CheckType
    from world.traits.models import Trait

FULL_WORTH_PERCENT = 100


def act_stat(check_type: CheckType) -> Trait | None:
    """The stat an act's own roll weighed most, or None when it weighed no stat.

    The STAT-type trait on ``check_type`` with the highest weight; ties go to the lowest
    trait row. The bonus check swaps this in for its own stat.
    """
    rows = [
        row
        for row in CheckTypeTrait.objects.filter(check_type=check_type).select_related("trait")
        if row.trait.trait_type == TraitType.STAT
    ]
    if not rows:
        return None
    return max(rows, key=lambda row: (row.weight, -row.trait_id)).trait


def _source_stat(source: str) -> Trait | None:
    """The stat staff set for ``source`` when the act rolled none of its own, else None."""
    row = ResonanceGainSourceStat.objects.filter(source=source).select_related("stat").first()
    return row.stat if row is not None else None


def _roll_bonus_check(
    sheet: CharacterSheet,
    affinity: Affinity,
    *,
    stat: Trait | None,
    source: str | None,
) -> CheckOutcome | None:
    """Roll the configured bonus check once; None when it is not configured.

    The stat is ``stat`` when given, else the stat staff set for ``source``, else the check
    type's own. No effort level is passed, so the roll develops nothing.
    """
    from world.checks.services import difficulty_points, perform_check  # noqa: PLC0415
    from world.magic.services.gain import get_resonance_gain_config  # noqa: PLC0415

    cfg = get_resonance_gain_config()
    if cfg.bonus_check_type_id is None:
        return None
    if stat is None and source is not None:
        stat = _source_stat(source)
    extra_traits = (
        (ExtraTraitTerm(trait=affinity.skill, weight=Decimal(1)),) if affinity.skill_id else ()
    )
    result = perform_check(
        sheet.character,
        check_type=cfg.bonus_check_type,
        target_difficulty=difficulty_points(cfg.bonus_difficulty_level),
        stat_override=stat.name if stat is not None else None,
        extra_traits=extra_traits,
    )
    return result.outcome


def _award_for(outcome: CheckOutcome | None) -> ResonanceCheckAward | None:
    """The staff award row for ``outcome``'s tier, or None for no outcome or no row."""
    if outcome is None:
        return None
    return ResonanceCheckAward.objects.filter(outcome_tier=outcome).first()


def roll_gain_bonus(
    sheet: CharacterSheet,
    affinity: Affinity,
    *,
    source: str,
    stat: Trait | None = None,
) -> GainBonus:
    """Roll the bonus check for one earned gain in ``affinity`` and say what it adds.

    ``stat`` is the stat of the act's own roll; without it the stat staff set for ``source``
    is used. With no bonus check configured nothing rolls and the bonus is 0. A result with
    no award row adds 0.
    """
    outcome = _roll_bonus_check(sheet, affinity, stat=stat, source=source)
    if outcome is None:
        return NO_GAIN_BONUS
    award = _award_for(outcome)
    return GainBonus(outcome=outcome, percent=award.gain_bonus_percent if award else 0)


def roll_spend_worth(
    sheet: CharacterSheet,
    affinity: Affinity,
    *,
    stat: Trait | None = None,
) -> int:
    """Roll the bonus check for one pull or kindled cast in ``affinity``; its worth in percent.

    The result is the awarded worth (100 with no award row), never below the affinity's own
    floor. With no bonus check configured nothing rolls and the worth is 100, with no floor.
    """
    outcome = _roll_bonus_check(sheet, affinity, stat=stat, source=None)
    if outcome is None:
        return FULL_WORTH_PERCENT
    award = _award_for(outcome)
    worth = award.spend_worth_percent if award else FULL_WORTH_PERCENT
    return max(worth, affinity.spend_worth_floor_percent)


def worth_clause(worth_by_affinity: Mapping[int, int]) -> str:
    """The plain sentence telling a player what their check made a pull worth, or "".

    One sentence per affinity whose worth was not 100 percent, named by the affinity's skill
    ("Your Villainy check made it worth 130 percent."). Empty when every worth is 100, so a
    pull with nothing configured reads exactly as it did.
    """
    changed = {
        pk: percent for pk, percent in worth_by_affinity.items() if percent != FULL_WORTH_PERCENT
    }
    if not changed:
        return ""
    affinities = Affinity.objects.filter(pk__in=changed).select_related("skill").order_by("pk")
    return " ".join(
        f"Your {a.skill.name if a.skill_id else a.name} check made it worth "
        f"{changed[a.pk]} percent."
        for a in affinities
    )
