"""Favor modifiers and the earning rate (#4333, design 1a and 1b).

Every being has one ``ModifierTarget`` in each of two categories,
``favor_invocation`` and ``favor_earning`` (``ModifierTarget.target_being``), and
each category has one "any being" target (``target_being`` null). Any modifier
source authored against those targets (a distinction effect, a condition effect,
a crafting recipe modifier, a covenant role bonus) reaches a character through
``favor_modifier_total``, the one reader.

Targets are created explicitly, never by a signal: by the Deity Editor's
``save_being``, by the backfill data migration ``0224_being_favor_targets``, and by
the seeds. A missing target reads as 0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.mechanics.constants import (
    FAVOR_EARNING_CATEGORY_NAME,
    FAVOR_INVOCATION_CATEGORY_NAME,
)
from world.worship.constants import FAVOR_EARNING_BASE_PERCENT

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import ModifierCategory, ModifierTarget
    from world.worship.models import DevotionStanding, WorshippedBeing

#: (category name, label used in target names, category description).
_FAVOR_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    (
        FAVOR_INVOCATION_CATEGORY_NAME,
        "favor invocation",
        "Difficulty points eased on the invocation check for a being (#4333).",
    ),
    (
        FAVOR_EARNING_CATEGORY_NAME,
        "favor earning",
        "Percentage points added to the earning rate with a being (#4333).",
    ),
)
ANY_BEING_TARGET_PREFIX = "Any being"
_TARGET_NAME_MAX_LENGTH = 100  # ModifierTarget.name


def _being_target_name(being: WorshippedBeing, label: str) -> str:
    """ "<being> <label>", the being's name shortened to fit the target name column."""
    suffix = f" {label}"
    return f"{being.name[: _TARGET_NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def _favor_category(name: str, description: str) -> ModifierCategory:
    from world.mechanics.models import ModifierCategory  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(
        name=name, defaults={"description": description}
    )
    return category


def ensure_being_modifier_targets(being: WorshippedBeing) -> list[ModifierTarget]:
    """Get-or-create ``being``'s two favor targets and the two "any being" targets.

    Idempotent. Returns the being's own targets, invocation first. A target that
    already exists keeps its name, so a renamed being keeps working; only the
    (category, being) pair identifies it.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    targets: list[ModifierTarget] = []
    for category_name, label, description in _FAVOR_CATEGORIES:
        category = _favor_category(category_name, description)
        ModifierTarget.objects.get_or_create(
            category=category,
            name=f"{ANY_BEING_TARGET_PREFIX} {label}",
            defaults={"target_being": None},
        )
        target = ModifierTarget.objects.filter(category=category, target_being=being).first()
        if target is None:
            # A target that already carries the being's name but lost its link
            # (a rolled-back release) is linked again rather than duplicated.
            target, _ = ModifierTarget.objects.get_or_create(
                category=category,
                name=_being_target_name(being, label),
                defaults={"target_being": being},
            )
            if target.target_being_id != being.pk:
                target.target_being = being
                target.save(update_fields=["target_being"])
        targets.append(target)
    return targets


def favor_modifier_total(sheet: CharacterSheet, being: WorshippedBeing, category_name: str) -> int:
    """The character's total of one favor category for ``being``, from every source.

    Sums, over every target in the category whose ``target_being`` is ``being`` or
    null (any being), ``get_modifier_total`` (eager ``CharacterModifier`` rows such
    as distinctions, crafted items, the equipment walk with covenant roles counted
    once) and ``get_condition_modifier_total`` (active conditions).
    """
    from world.conditions.services import get_condition_modifier_total  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    targets = ModifierTarget.objects.filter(category__name=category_name, is_active=True).filter(
        Q(target_being=being) | Q(target_being__isnull=True)
    )
    return sum(
        get_modifier_total(sheet, target) + get_condition_modifier_total(sheet, target)
        for target in targets.select_related("category")
    )


def active_patronage_of(sheet: CharacterSheet, being: WorshippedBeing) -> DevotionStanding | None:
    """The character's active patronage of ``being`` (they are its Chosen), or None."""
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    return DevotionStanding.objects.filter(
        character_sheet=sheet,
        being=being,
        valence__isnull=False,
        released_at__isnull=True,
    ).first()


def earning_rate(sheet: CharacterSheet, being: WorshippedBeing) -> int:
    """The percentage applied to all favor ``sheet`` earns with ``being`` (design 1a).

    100, plus ``ChosenFavorConfig.earn_bonus_percent`` for an active patronage of
    the being, plus the character's favor earning total for it. Never below 0.
    """
    from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

    rate = FAVOR_EARNING_BASE_PERCENT
    if active_patronage_of(sheet, being) is not None:
        rate += get_chosen_favor_config().earn_bonus_percent
    rate += favor_modifier_total(sheet, being, FAVOR_EARNING_CATEGORY_NAME)
    return max(rate, 0)


def scale_by_earning_rate(sheet: CharacterSheet, being: WorshippedBeing, amount: int) -> int:
    """``amount`` of favor at the character's earning rate, rounded down."""
    return amount * earning_rate(sheet, being) // 100
