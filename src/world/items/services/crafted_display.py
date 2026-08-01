"""Crafted-provenance display line (#2878).

The examine layer at the bottom of an item's description: the mechanical
line rendered as prose ("Of divine quality, quite menacing and slightly
alluring."), then the persona-scoped credits ("Designed by X; crafted by
Y."). The ladders' names ARE the display grammar — no translation layer.

Shared by the telnet appearance section and the web serializer field so the
two surfaces can never drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.crafting.models import ItemAccent
    from world.items.models import ItemInstance


def _accent_phrase(accent: ItemAccent) -> str:
    adjective = accent.target.styleable_adjective or accent.target.name
    return f"{accent.level.name} {adjective}"


def _primary_or_none(sheet: object | None) -> object | None:
    """The sheet's PRIMARY persona, or None (broken invariant / no sheet)."""
    if sheet is None:
        return None
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        return sheet.primary_persona
    except Persona.DoesNotExist:
        return None


def _join_prose(parts: list[str]) -> str:
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def crafted_provenance_line(instance: ItemInstance) -> str | None:
    """The mechanical + credits line for a crafted piece, or None.

    None for items with no quality tier, no accents, and no credits —
    found/spawned objects stay prose-only.
    """
    sentences: list[str] = []

    quality = instance.quality_tier
    accents = list(instance.accents.select_related("target", "level"))
    accent_prose = _join_prose([_accent_phrase(a) for a in accents])
    if quality is not None and accents:
        sentences.append(f"Of {quality.name.lower()} quality, {accent_prose}.")
    elif quality is not None:
        sentences.append(f"Of {quality.name.lower()} quality.")
    elif accents:
        sentences.append(f"{accent_prose[0].upper()}{accent_prose[1:]}.")

    # Credits: the #2066 dual-provenance fields on the instance, with the
    # documented fallback (persona_display → sheet.primary_persona). Renders
    # "Crafted by X, Designed by Y", collapsing when equal (#2066 convention).
    maker = instance.crafter_persona_display or _primary_or_none(instance.crafter_character_sheet)
    designer = instance.designer_persona_display or _primary_or_none(
        instance.designer_character_sheet
    )
    if maker is not None and designer is not None and designer.pk != maker.pk:
        sentences.append(f"Crafted by {maker.name}, designed by {designer.name}.")
    elif maker is not None:
        sentences.append(f"Crafted by {maker.name}.")
    elif designer is not None:
        sentences.append(f"Designed by {designer.name}.")

    if not sentences:
        return None
    return " ".join(sentences)
