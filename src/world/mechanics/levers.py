"""The IC levers a distinction may pull: one reader each, nowhere else.

Five levers scale something (#4394): income at the allowance and asset-collection payouts,
reputation gain where a society's or an organization's regard rises, relationship gain where
affection shifts, comfort where a residence's comfort is read for one character, fatigue cost
where an action's fatigue is charged. Two more are yes or no: sight through a mask (#4396,
read where an identification is contested) and teaching herself magic (#5326, read where
weekly training is allocated, ``self_teaching_granted`` below). Every reader goes through
``get_modifier_total`` (ADR-0278: one walk, never a second), so a distinction effect, an
achievement reward or a condition on the lever's target all count, and the sheet's modifier
breakdown names them.

The rows themselves are content (``ModifierCategory``/``ModifierTarget`` are content-repo
owned, #2698): a lever whose target is not authored reads as 0 and the seam behaves exactly as
it did before the lever existed. ``world.seeds.levers.ensure_lever_targets`` authors them on a
dev or E2E database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.mechanics.constants import SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def lever_total(sheet: CharacterSheet, category_name: str, target_name: str) -> int:
    """The character's total on one lever target, 0 when the target is not authored."""
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    target = ModifierTarget.objects.filter(category__name=category_name, name=target_name).first()
    if target is None:
        return 0
    return get_modifier_total(sheet, target)


def self_teaching_granted(sheet: CharacterSheet) -> bool:
    """Whether the character may teach herself magical skills (#5326).

    Yes or no: any positive total on the self-teaching target grants it, so a value of 1 and a
    value of 5 are the same, and so are one source and two. A target staff have not authored
    reads as 0, so nobody is granted it.
    """
    return lever_total(sheet, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME) > 0


def scale_by_percent(base: int, percent: int, *, floor: int = 0) -> int:
    """``base`` scaled by ``100 + percent`` percent, whole units, never below ``floor``.

    A lever of 0 returns ``base`` untouched, so a seam with no lever authored is byte for
    byte what it was. Only ever applied to an amount being gained or charged, never to a
    loss: a reputation sting or a conflict bump is not a gain.
    """
    if percent == 0:
        return base
    return max(floor, base * (100 + percent) // 100)
