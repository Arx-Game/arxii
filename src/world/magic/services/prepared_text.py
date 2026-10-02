"""Resolve Audere text: character, then patron variant, then tier (#4101)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.types.prepared_text import CrossingText, SurgeText

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.audere import AudereThreshold
    from world.magic.audere_majora import (
        AudereMajoraCrossing,
        AudereMajoraFaithVariant,
        AudereMajoraThreshold,
    )
    from world.magic.models.prepared_text import CharacterCrossingText

__all__ = [
    "CrossingText",
    "SurgeText",
    "consume_prepared_crossing_text",
    "may_prepare_text_for",
    "resolve_crossing_text",
    "resolve_surge_text",
    "unused_prepared_crossing_text",
]


def unused_prepared_crossing_text(sheet: CharacterSheet) -> CharacterCrossingText | None:
    """The character's own not-yet-fired prepared crossing text, if any."""
    from world.magic.models.prepared_text import CharacterCrossingText  # noqa: PLC0415

    return CharacterCrossingText.objects.filter(
        character_sheet=sheet, crossing__isnull=True
    ).first()


def _first(*values: str) -> str:
    return next((v for v in values if v and v.strip()), "")


def resolve_crossing_text(
    sheet: CharacterSheet,
    threshold: AudereMajoraThreshold,
    variant: AudereMajoraFaithVariant | None,
) -> CrossingText:
    """Field-by-field layering: character, then patron variant, then tier."""
    prepared = unused_prepared_crossing_text(sheet)
    own_vision = prepared.vision_text if prepared else ""
    own_room = prepared.manifestation_text if prepared else ""
    own_title = prepared.deed_title if prepared else ""
    return CrossingText(
        vision=_first(own_vision, variant.vision_text if variant else "", threshold.vision_text),
        manifestation=_first(
            own_room, variant.manifestation_text if variant else "", threshold.manifestation_text
        ),
        deed_title=_first(own_title, threshold.deed_title),
        prepared=bool(_first(own_vision, own_room, own_title)),
    )


def resolve_surge_text(sheet: CharacterSheet | None, threshold: AudereThreshold) -> SurgeText:
    """Field-by-field layering: character, then tier (no patron layer for surges)."""
    from world.magic.models.prepared_text import CharacterSurgeText  # noqa: PLC0415

    own = ""
    if sheet is not None:
        row = CharacterSurgeText.objects.filter(character_sheet=sheet).first()
        own = row.surge_text if row else ""
    return SurgeText(
        text=_first(own, threshold.surge_manifestation_text).strip(),
        prepared=bool(own.strip()),
    )


def consume_prepared_crossing_text(sheet: CharacterSheet, crossing: AudereMajoraCrossing) -> None:
    """Mark the character's unused prepared crossing text used by ``crossing``.

    A no-op if nothing was prepared — the generic/patron text already fired.
    """
    prepared = unused_prepared_crossing_text(sheet)
    if prepared is None:
        return
    prepared.crossing = crossing
    prepared.save(update_fields=["crossing", "updated_at"])


def may_prepare_text_for(account: AccountDB | None, sheet: CharacterSheet) -> bool:
    """Staff, or the character's table GM (spec decision 9)."""
    if account is None:
        return False
    if account.is_staff:
        return True
    from world.gm.services import account_is_table_gm_for_sheet  # noqa: PLC0415

    return account_is_table_gm_for_sheet(account, sheet)
