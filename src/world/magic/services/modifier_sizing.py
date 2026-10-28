"""A technique's buffs and debuffs carry a level and a size (#4551, #4594).

* ``CastLevelTable`` / ``load_cast_level_table`` - the cast's effective power picks a
  level (``CastPowerLevel`` rows) and its outcome shifts it (``CastOutcomeLevelShift``
  rows). The applied condition keeps that level and its authored size, and the check
  lane's value table turns the pair into points (the stat lane's for a stat, #4726).
  The target's level is never read.
* ``caster_vow_step`` - a vowed caster's size step (#4747): her vow thread's shown
  level and the matching technique specialty's share, when her engaged vow specializes
  in one of the cast technique's functions.
* ``applied_condition_size_warnings`` - the admin size check: a buff's authored size
  should match how its technique spends its power.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from world.checks.constants import ModifierSize
from world.checks.types import round_half_up
from world.conditions.models import ConditionCheckModifier, ConditionModifierEffect
from world.magic.models.modifier_level import CastOutcomeLevelShift, CastPowerLevel
from world.magic.models.techniques import TechniqueAppliedCondition
from world.traits.models import TraitType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

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


@dataclass(frozen=True)
class VowStep:
    """A caster's vow size step on one cast (#4747): where it is valued and how much.

    ``level`` is her vow thread's shown level; ``tenths`` is the step's share in
    integer tenths (10 = one whole size step), from the matching specialty row's
    ``multiplier_tenths``.
    """

    level: int
    tenths: int


def caster_vow_step(
    caster: ObjectDB | None,  # noqa: OBJECTDB_PARAM - the cast's source_character
    technique: Technique,
) -> VowStep | None:
    """``caster``'s vow size step on a cast of ``technique``, or None (#4747).

    The vow is the one ``_resolve_source_vow_anchor`` stamps as ``source_vow``: the
    first of her currently engaged roles. It steps when that role, its resolved
    resonance sub-role or its anchor has a ``CovenantRoleTechniqueSpecialty`` row
    whose function is one of ``technique``'s function tags. Only the one-size-up shape
    is fixed here; every amount is staff-tuned data:

    * the level is the shown level of her COVENANT_ROLE thread on the anchor, never
      capped by the buff's own level (owner ruling 2026-10-27);
    * the share is the matching row's ``multiplier_tenths``, the same dial that scales
      the specialty's cast power; when the role and its sub-role (or anchor) both
      match, the larger multiplier counts;
    * a secondary vow (first when her primary is disengaged) multiplies those tenths
      by ``SecondaryVowConfig.potency_tenths / 10``, rounded half up, as the
      specialty layer scales a secondary everywhere else. Its level stays whole.

    None when there is no caster or engaged vow, no matching row, no thread, the
    level is 0, or the share comes to 0. Called once per cast, only when a row is
    sized.
    """
    if caster is None:
        return None
    functions = {tag.function for tag in technique.cached_function_tags}
    if not functions:
        return None
    try:
        engaged = caster.covenant_roles.currently_engaged_roles_with_flags()
    except (AttributeError, ObjectDoesNotExist):
        # No covenant_roles handler (a test double) or no CharacterSheet (an NPC):
        # no engaged vow, as in _resolve_source_vow_anchor.
        return None
    if not engaged:
        return None
    role, is_secondary = engaged[0]
    anchor_id = role.parent_role_id or role.pk

    from world.covenants.models import CovenantRoleTechniqueSpecialty  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.services.threads import shown_thread_level  # noqa: PLC0415

    multipliers = CovenantRoleTechniqueSpecialty.objects.filter(
        covenant_role_id__in={role.pk, anchor_id}, function__in=functions
    ).values_list("multiplier_tenths", flat=True)
    tenths = max(multipliers, default=0)
    if not tenths:
        return None
    stored = (
        Thread.objects.filter(
            owner_id=caster.pk,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role_id=anchor_id,
            retired_at__isnull=True,
        )
        .values_list("level", flat=True)
        .first()
    )
    level = shown_thread_level(stored) if stored else 0
    if not level:
        return None
    if is_secondary:
        from world.covenants.services import secondary_vow_config  # noqa: PLC0415

        tenths = round_half_up(Decimal(tenths) * secondary_vow_config().potency_tenths / 10)
    if not tenths:
        return None
    return VowStep(level=level, tenths=tenths)


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


def _size_budget_warning(
    row: TechniqueAppliedCondition, technique: Technique, effect_count: int
) -> str | None:
    """Explain when a condition's size exceeds or underspends its power budget."""
    size = row.modifier_size
    if size is None:
        return None
    size_label = ModifierSize(size).label
    ceiling = _expected_size_ceiling(row, effect_count)
    if size > ceiling:
        others = effect_count - 1
        return (
            f"{row.condition.name} is sized {size_label}, but {technique.name} does "
            f"{others} other thing{'s' if others != 1 else ''} as well, so this buff "
            f"shares the cast's power: at most {ModifierSize(ceiling).label}"
            f"{' with narrow use' if row.narrow_use else ''}."
        )
    if effect_count <= 1 and size < ModifierSize.LARGE:
        return (
            f"{row.condition.name} is sized {size_label}, but it is everything "
            f"{technique.name} does, so it gets the whole power budget: Large."
        )
    return None


def applied_condition_size_warnings(technique: Technique) -> list[str]:
    """Plain warnings where a buff's size doesn't match how its technique spends power.

    The size budget: a technique that only buffs puts its whole budget into the buff,
    so the buff is Large; one that does something else as well splits it, so the buff
    is Minor or Moderate; narrow use pays for one step more, up to Exceptional. A
    warning, never a refusal: staff may have a reason. A sized row whose condition
    changes no check and no stat (#4726: a stat target is valued from the stat lane)
    also warns, since the size has nothing to act on yet.
    """
    effect_count = _technique_effect_count(technique)
    sized_condition_ids = {
        row.condition_id
        for row in technique.cached_condition_applications
        if row.modifier_size is not None
    }
    # One query for every sized condition that changes a check, and one for every one that
    # changes a stat (#4726), template- or stage-level.
    checked_condition_ids: set[int] = set()
    if sized_condition_ids:
        in_sized = Q(condition_id__in=sized_condition_ids) | Q(
            stage__condition_id__in=sized_condition_ids
        )
        acting_rows = [
            *ConditionCheckModifier.objects.filter(in_sized).values_list(
                "condition_id", "stage__condition_id"
            ),
            *ConditionModifierEffect.objects.filter(
                in_sized, modifier_target__target_trait__trait_type=TraitType.STAT
            ).values_list("condition_id", "stage__condition_id"),
        ]
        for condition_id, stage_condition_id in acting_rows:
            checked_condition_ids.update(
                cid for cid in (condition_id, stage_condition_id) if cid is not None
            )
    warnings: list[str] = []
    for row in technique.cached_condition_applications:
        if row.modifier_size is None:
            continue
        size_label = ModifierSize(row.modifier_size).label
        budget_warning = _size_budget_warning(row, technique, effect_count)
        if budget_warning is not None:
            warnings.append(budget_warning)
        if row.condition_id not in checked_condition_ids:
            warnings.append(
                f"{row.condition.name} is sized {size_label}, but it changes no check "
                "or stat, so its size has nothing to act on yet."
            )
    return warnings


def is_sized_row(row: object) -> bool:
    """Whether ``row`` is a technique's applied condition with an authored size."""
    return isinstance(row, TechniqueAppliedCondition) and row.modifier_size is not None
