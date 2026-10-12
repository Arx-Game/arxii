"""Combat target bonus from character sheets."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


# ---------------------------------------------------------------------------
# Equipped-gear combat contribution helpers (#508, Task 7)
# ---------------------------------------------------------------------------
#
# Pure read helpers over ``character.equipped_items`` (the iterable
# CharacterEquipmentHandler, whose rows arrive with item_instance + template +
# quality_tier select_related, so reading effective_* during iteration is
# query-free). They do NOT mutate combat damage logic — that wiring is Tasks
# 8/9. ``_select_equipped_weapon`` is kept separate so the weapon-durability
# decrement task can reuse the same selection.


def _combat_target_bonus(sheet: object, target_name: str, level_override: int | None = None) -> int:
    """get_modifier_total for a named combat ModifierTarget; 0 if the row isn't seeded.

    Combat never hard-depends on seed order (mirrors covenant_level_bonus's
    config-is-None → 0). The target's stat category routes the covenant-role
    equipment walk into the total.

    When ``level_override`` is not supplied, computes the bond-adjusted level via
    ``bond_adjusted_level(sheet)`` (#1165). An unbonded sheet returns None, which
    falls through to ``sheet.current_level`` inside ``covenant_role_bonus`` — zero
    query overhead for the common (non-bonded) case because bond_adjusted_level
    returns None after the fast active-bond check.

    When ``level_override`` is supplied explicitly (e.g. caller already computed
    it), that value is passed directly without a redundant bond lookup.
    """
    from typing import cast  # noqa: PLC0415

    from world.covenants.mentorship import bond_adjusted_level  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    try:
        target = ModifierTarget.objects.get(name=target_name)
    except ModifierTarget.DoesNotExist:
        return 0
    sheet_typed = cast("CharacterSheet", sheet)
    override = level_override if level_override is not None else bond_adjusted_level(sheet_typed)
    return get_modifier_total(sheet, target, level_override=override)
