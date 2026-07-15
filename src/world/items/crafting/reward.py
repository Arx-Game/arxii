"""Crafting reward loop: a masterwork makes its maker a little famous (#2243).

Top-tier work is socially inert without this — quality only fed mechanical stat
modifiers. A masterwork craft now creates a solo ``LegendEntry`` (a deed) for the
crafter's persona, so fine work attaches to the maker's renown track record (the
"famous for forging the alaricite blade" fantasy). Magnitudes are PLACEHOLDER.

Lives crafting-side and imports the legend engine (items → societies is the
allowed direction; societies is the reusable renown primitive, ADR-0010).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.crafting.constants import (
    MASTERWORK_DEED_BASE_VALUE,
    MASTERWORK_STAT_MULTIPLIER_THRESHOLD,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance, QualityTier


def is_masterwork(tier: QualityTier | None) -> bool:
    """Whether a resolved quality tier counts as masterwork (#2243).

    Callers should pair this with an explicit ``tier is not None`` narrowing before
    passing ``tier`` on (a masterwork is never ``None``, but the type checker only
    narrows through the plain ``is not None`` check, not this predicate).
    """
    return tier is not None and tier.stat_multiplier >= MASTERWORK_STAT_MULTIPLIER_THRESHOLD


def award_masterwork_renown(
    *,
    crafter_character_sheet: CharacterSheet,
    tier: QualityTier,
    item_label: str,
    item_instance: ItemInstance | None = None,
) -> None:
    """Grant the crafter a solo legend deed for a masterwork-quality craft (#2243).

    No-op if the sheet has no persona to attach renown to. Reuses the shared
    ``create_solo_deed`` seam, so the deed flows through the same legend/renown
    engine as any other notable act. If ``item_instance`` is provided, the
    deed is linked to the item via the ``legend_deeds`` M2M (#2359).
    """
    from world.societies.models import LegendSourceType  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    persona = crafter_character_sheet.primary_persona
    if persona is None:
        return
    source_type, _ = LegendSourceType.objects.get_or_create(
        name="Crafting",
        defaults={"description": "Masterwork crafting — fine goods that make a name."},
    )
    entry = create_solo_deed(
        persona,
        f"Crafted a masterwork {item_label}",
        source_type,
        MASTERWORK_DEED_BASE_VALUE,
        description=f"PLACEHOLDER — {tier.name}-quality work worthy of note.",
    )
    if item_instance is not None:
        item_instance.legend_deeds.add(entry)
