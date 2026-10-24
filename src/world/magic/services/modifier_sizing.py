"""A technique's buffs and debuffs carry a level and a size (#4551, #4594).

* ``CastLevelTable`` / ``load_cast_level_table`` - the cast's effective power picks a
  level (``CastPowerLevel`` rows) and its outcome shifts it (``CastOutcomeLevelShift``
  rows). The applied condition keeps that level and its authored size, and the check
  lane's value table turns the pair into points. The target's level is never read.
* ``applied_condition_size_warnings`` - the admin size check: a buff's authored size
  should match how its technique spends its power.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db.models import Q

from world.checks.constants import ModifierSize
from world.conditions.models import ConditionCheckModifier
from world.magic.models.modifier_level import CastOutcomeLevelShift, CastPowerLevel
from world.magic.models.techniques import TechniqueAppliedCondition

if TYPE_CHECKING:
    from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class CastLevelTable:
    """The power-to-level and outcome-shift rows, loaded once per cast."""

    power_levels: tuple[tuple[int, int], ...] = ()
    outcome_shifts: dict[int, int] = field(default_factory=dict)

    def level_for(self, *, effective_power: int, success_level: int) -> int | None:
        """The level a cast at ``effective_power`` landing ``success_level`` applies at.

        None when the cast is weaker than every power row (or there are none): its
        modifiers then keep their flat values. The outcome shift never takes the level
        below 1.
        """
        thresholds = [min_power for min_power, _ in self.power_levels]
        index = bisect_right(thresholds, effective_power)
        if index == 0:
            return None
        level = self.power_levels[index - 1][1] + self.outcome_shifts.get(success_level, 0)
        return max(1, level)


def load_cast_level_table() -> CastLevelTable:
    """Load every ``CastPowerLevel`` and ``CastOutcomeLevelShift`` row (two queries)."""
    return CastLevelTable(
        power_levels=tuple(
            CastPowerLevel.objects.order_by("min_power").values_list("min_power", "level")
        ),
        outcome_shifts=dict(
            CastOutcomeLevelShift.objects.values_list("success_level", "level_shift")
        ),
    )


def sized_modifier_level(
    row: object,
    *,
    effective_power: int,
    success_level: int,
    table: CastLevelTable | None,
) -> tuple[int | None, int | None]:
    """The (level, size) a cast stamps on the condition ``row`` applies.

    Only a row that authors a ``modifier_size`` is sized; any other applied-condition
    row (a variant, a draft, a signature bonus, a vow's added condition) reads as
    (None, None) and its condition keeps its flat values. A sized row on a cast weaker
    than every power row also stays unsized.
    """
    if not isinstance(row, TechniqueAppliedCondition) or table is None:
        return None, None
    size = row.modifier_size
    if size is None:
        return None, None
    level = table.level_for(effective_power=effective_power, success_level=success_level)
    if level is None:
        return None, None
    return level, size


def _technique_effect_count(technique: Technique) -> int:
    """How many cast payload rows ``technique`` spends its power on."""
    return (
        len(technique.cached_condition_applications)
        + len(technique.cached_damage_profiles)
        + len(technique.cached_capability_grants)
        + len(technique.cached_removed_conditions)
        + len(technique.cached_treatments)
        + (1 if technique.cached_morale_effect is not None else 0)
    )


def _expected_size_ceiling(row: TechniqueAppliedCondition, effect_count: int) -> int:
    """The largest size the size budget allows ``row`` (#4551 section 5.3, item 4)."""
    ceiling = ModifierSize.LARGE if effect_count <= 1 else ModifierSize.MODERATE
    if row.narrow_use:
        ceiling += 1
    return min(ceiling, ModifierSize.EXCEPTIONAL)


def applied_condition_size_warnings(technique: Technique) -> list[str]:
    """Plain warnings where a buff's size doesn't match how its technique spends power.

    The size budget: a technique that only buffs puts its whole budget into the buff,
    so the buff is Large; one that does something else as well splits it, so the buff
    is Minor or Moderate; narrow use pays for one step more, up to Exceptional. A
    warning, never a refusal: staff may have a reason. A sized row whose condition
    changes no check also warns, since the size has nothing to act on yet.
    """
    effect_count = _technique_effect_count(technique)
    sized_condition_ids = {
        row.condition_id
        for row in technique.cached_condition_applications
        if row.modifier_size is not None
    }
    # One query for every sized condition that changes a check, template- or stage-level.
    checked_condition_ids: set[int] = set()
    if sized_condition_ids:
        for condition_id, stage_condition_id in ConditionCheckModifier.objects.filter(
            Q(condition_id__in=sized_condition_ids) | Q(stage__condition_id__in=sized_condition_ids)
        ).values_list("condition_id", "stage__condition_id"):
            checked_condition_ids.update(
                cid for cid in (condition_id, stage_condition_id) if cid is not None
            )
    warnings: list[str] = []
    for row in technique.cached_condition_applications:
        if row.modifier_size is None:
            continue
        size_label = ModifierSize(row.modifier_size).label
        ceiling = _expected_size_ceiling(row, effect_count)
        if row.modifier_size > ceiling:
            others = effect_count - 1
            warnings.append(
                f"{row.condition.name} is sized {size_label}, but {technique.name} does "
                f"{others} other thing{'s' if others != 1 else ''} as well, so this buff "
                f"shares the cast's power: at most {ModifierSize(ceiling).label}"
                f"{' with narrow use' if row.narrow_use else ''}."
            )
        elif effect_count <= 1 and row.modifier_size < ModifierSize.LARGE:
            warnings.append(
                f"{row.condition.name} is sized {size_label}, but it is everything "
                f"{technique.name} does, so it gets the whole power budget: Large."
            )
        if row.condition_id not in checked_condition_ids:
            warnings.append(
                f"{row.condition.name} is sized {size_label}, but it changes no check, "
                "so its size has nothing to act on yet."
            )
    return warnings


def is_sized_row(row: object) -> bool:
    """Whether ``row`` is a technique's applied condition with an authored size."""
    return isinstance(row, TechniqueAppliedCondition) and row.modifier_size is not None
