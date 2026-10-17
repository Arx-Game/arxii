"""The five IC levers a distinction may pull (#4394): one reader each, nowhere else.

A lever is a ``ModifierCategory`` whose targets are read at exactly one seam: income at the
allowance and asset-collection payouts, reputation gain where a society's or an organization's
regard rises, relationship gain where affection shifts, comfort where a residence's comfort is
read for one character, fatigue cost where an action's fatigue is charged. Every reader goes
through ``get_modifier_total`` (ADR-0278: one walk, never a second), so a distinction effect,
an achievement reward or a condition on the lever's target all count, and the sheet's modifier
breakdown names them.

The rows themselves are content (``ModifierCategory``/``ModifierTarget`` are content-repo
owned, #2698): a lever whose target is not authored reads as 0 and the seam behaves exactly as
it did before the lever existed. ``world.seeds.levers.ensure_lever_targets`` authors them on a
dev or E2E database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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


def scale_by_percent(base: int, percent: int, *, floor: int = 0) -> int:
    """``base`` scaled by ``100 + percent`` percent, whole units, never below ``floor``.

    A lever of 0 returns ``base`` untouched, so a seam with no lever authored is byte for
    byte what it was. Only ever applied to an amount being gained or charged, never to a
    loss: a reputation sting or a conflict bump is not a gain.
    """
    if percent == 0:
        return base
    return max(floor, base * (100 + percent) // 100)
