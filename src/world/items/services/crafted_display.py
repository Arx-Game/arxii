"""Crafted-provenance display line (#2878).

The examine layer at the bottom of an item's description: the mechanical
line rendered as prose ("Of divine quality, quite menacing and slightly
alluring."), then the persona-scoped credits ("Designed by X; crafted by
Y."). The ladders' names ARE the display grammar — no translation layer.

Shared by the telnet appearance section and the web serializer field so the
two surfaces can never drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.crafting.models import ItemAccent
    from world.items.models import ItemInstance
    from world.scenes.models import Persona


def _accent_phrase(accent: ItemAccent) -> str:
    adjective = accent.target.styleable_adjective or accent.target.name
    return f"{accent.level.name} {adjective}"


def _primary_or_none(sheet: CharacterSheet | None) -> Persona | None:
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


def _credit_sentences(
    instance: ItemInstance, maker: Persona | None, designer: Persona | None
) -> list[str]:
    """ "Made by X for Y." and "Designed by Z." (one "Made and designed by X" when the maker
    also wrote the design)."""
    made_for = instance.dedicated_to_persona
    for_clause = f" for {made_for.name}" if made_for is not None else ""
    same = maker is not None and designer is not None and designer.pk == maker.pk
    if same:
        return [f"Made and designed by {maker.name}{for_clause}."]
    sentences: list[str] = []
    if maker is not None:
        sentences.append(f"Made by {maker.name}{for_clause}.")
    elif made_for is not None:
        sentences.append(f"Made for {made_for.name}.")
    if designer is not None:
        sentences.append(f"Designed by {designer.name}.")
    return sentences


def _facet_workers(instance: ItemInstance) -> list[str]:
    """Names of the artists who did crafting-service work on it, in order, once each."""
    workers: list[str] = []
    for sale in instance.cached_service_sales:
        seller = sale.seller_persona
        if seller is not None and seller.name not in workers:
            workers.append(seller.name)
    return workers


@dataclass(frozen=True)
class CreditedNames:
    """Who examine names on a piece (#4512): the maker, the designer and the facet workers."""

    maker: str | None
    designer: str | None
    facet_workers: list[str]


def _credit_personas(instance: ItemInstance) -> tuple[Persona | None, Persona | None]:
    """The maker's and the designer's personas, with the documented fallback
    (persona_display, then the sheet's primary persona)."""
    maker = instance.crafter_persona_display or _primary_or_none(instance.crafter_character_sheet)
    designer = instance.designer_persona_display or _primary_or_none(
        instance.designer_character_sheet
    )
    return maker, designer


def credited_names(instance: ItemInstance) -> CreditedNames:
    """The names examine credits on ``instance`` (the commission form previews them)."""
    maker, designer = _credit_personas(instance)
    return CreditedNames(
        maker=maker.name if maker is not None else None,
        designer=designer.name if designer is not None else None,
        facet_workers=_facet_workers(instance),
    )


def _facet_work_and_lineage(instance: ItemInstance) -> list[str]:
    """ "Facet work by W." for each artist who did crafting-service work on it, and
    "Worked from <name>." for what it was made from (marked when that is gone)."""
    sentences: list[str] = []
    workers = _facet_workers(instance)
    if workers:
        sentences.append(f"Facet work by {_join_prose(workers)}.")
    for row in instance.cached_lineage:
        source = row.source_item
        gone = source is None or source.destroyed_at is not None
        sentences.append(
            f"Worked from {row.source_name}, which is gone."
            if gone
            else f"Worked from {row.source_name}."
        )
    return sentences


def _trophy_and_keepsake(instance: ItemInstance) -> list[str]:
    """ "Trophy of <deed>." for each active deed the piece is linked to, and the holder's
    keepsake words when they chose to show them (#4530). The words are the player's own and
    are shown as written; examine never says what a keepsake is worth."""
    sentences = [f"Trophy of {deed.title}." for deed in instance.cached_trophy_deeds]
    holder = instance.holder_character_sheet
    if holder is None:
        return sentences
    keepsake = next(
        (row for row in instance.cached_shown_keepsakes if row.character_sheet_id == holder.pk),
        None,
    )
    if keepsake is not None and keepsake.text:
        persona = _primary_or_none(holder)
        who = persona.name if persona is not None else "its holder"
        sentences.append(f"Kept as a keepsake by {who}: {keepsake.text}")
    return sentences


def _gone_sentence(instance: ItemInstance) -> str:
    """Why a piece that is no longer in play is gone, from the note on its last event: the
    record of who made and designed it outlives it (#4512)."""
    event = instance.ownership_events.order_by("-created_at", "-pk").first()
    # A give-up note reads "Given up to <being>: <reason>"; examine names the place, not the
    # machine reason after the colon.
    note = (
        event.notes.partition(":")[0].strip().rstrip(".")
        if event is not None and event.notes
        else ""
    )
    return f"Gone: {note}." if note else "It is gone."


def crafted_provenance_line(instance: ItemInstance) -> str | None:
    """The mechanical + credits line for a crafted piece, or None.

    None for items with no quality tier, no accents, and no credits —
    found/spawned objects stay prose-only.
    """
    sentences: list[str] = []

    quality = instance.quality_tier
    # cached_item_accents (not a fresh query): free when the equipment-walk
    # prefetch populated it, and cached on the idmapper instance thereafter —
    # keeps the warm-list endpoints at their locked query counts.
    accents = instance.cached_item_accents
    accent_prose = _join_prose([_accent_phrase(a) for a in accents])
    if quality is not None and accents:
        sentences.append(f"Of {quality.name.lower()} quality, {accent_prose}.")
    elif quality is not None:
        sentences.append(f"Of {quality.name.lower()} quality.")
    elif accents:
        sentences.append(f"{accent_prose[0].upper()}{accent_prose[1:]}.")

    # Form (#2907): prose skin by wear family — garments have a "cut",
    # jewelry a "setting", everything else a "silhouette".
    silhouette = instance.effective_silhouette
    if silhouette is not None:
        sentences.append(f"Its {silhouette.prose_noun} is the {silhouette.name.lower()}.")

    # Credits (#2066 dual provenance, #4512): "Made by X for Y. Designed by Z. Facet work
    # by W." The designer is credited only when they wrote text; the maker's tie and the
    # fee are not shown. A piece worked from another item lists it, marked when it is gone.
    maker, designer = _credit_personas(instance)
    sentences.extend(_credit_sentences(instance, maker, designer))
    sentences.extend(_facet_work_and_lineage(instance))
    sentences.extend(_trophy_and_keepsake(instance))
    if instance.destroyed_at is not None:
        sentences.append(_gone_sentence(instance))

    if not sentences:
        return None
    return " ".join(sentences)
