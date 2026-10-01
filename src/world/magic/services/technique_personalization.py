"""A character's own name, look and price for a technique they hold (#4099, ADR-4099).

Personalization lives on the hold (``CharacterTechnique``), never on the shared
catalog row. Names are display only: every lookup keeps reading ``Technique.name``.
All reads go through the cached ``character.techniques`` handler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import unicodedata

from django.db import transaction

from core.identifier_dashes import contains_dash
from world.magic.constants import (
    CUSTOM_TECHNIQUE_DESCRIPTION_MAX_LENGTH,
    CUSTOM_TECHNIQUE_NAME_MAX_LENGTH,
)
from world.magic.exceptions import InvalidPersonalText

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import (
        CharacterTechnique,
        MotifResonance,
        Resonance,
        Restriction,
        Technique,
    )

_MARKUP_CHARACTER = "|"


def _has_control_character(value: str, *, allow_newline: bool) -> bool:
    return any(
        # "Cc" is stdlib unicodedata's own category code, not an app identifier.
        unicodedata.category(ch) == "Cc"  # noqa: STRING_LITERAL
        and not (allow_newline and ch == "\n")
        for ch in value
    )


def clean_custom_technique_name(value: str) -> str:
    """Normalize a player's own technique name; ``""`` means use the catalog name."""
    cleaned = " ".join(value.split())
    if len(cleaned) > CUSTOM_TECHNIQUE_NAME_MAX_LENGTH:
        msg = f"A technique's name is at most {CUSTOM_TECHNIQUE_NAME_MAX_LENGTH} characters."
        raise InvalidPersonalText(msg)
    if contains_dash(cleaned):
        msg = "Use a plain hyphen in a technique's name, not a long dash."
        raise InvalidPersonalText(msg)
    if _MARKUP_CHARACTER in cleaned or _has_control_character(cleaned, allow_newline=False):
        msg = "A technique's name cannot contain '|' or control characters."
        raise InvalidPersonalText(msg)
    return cleaned


def clean_custom_technique_description(value: str) -> str:
    """Normalize a player's own technique description; ``""`` means the catalog's."""
    cleaned = value.strip()
    if len(cleaned) > CUSTOM_TECHNIQUE_DESCRIPTION_MAX_LENGTH:
        msg = (
            "A technique's description is at most "
            f"{CUSTOM_TECHNIQUE_DESCRIPTION_MAX_LENGTH} characters."
        )
        raise InvalidPersonalText(msg)
    if _has_control_character(cleaned, allow_newline=True):
        msg = "A technique's description cannot contain control characters."
        raise InvalidPersonalText(msg)
    return cleaned


def hold_display_name(hold: CharacterTechnique | None, *, fallback: str) -> str:
    """The owner's name for a hold, else ``fallback`` (a variant name or the catalog name)."""
    if hold is not None and hold.custom_name:
        return hold.custom_name
    return fallback


def technique_display_name(character, technique: Technique, *, fallback: str | None = None) -> str:
    """What ``character`` calls ``technique``: their own name, else ``fallback``, else catalog."""
    hold = character.techniques.hold_for(technique)
    return hold_display_name(hold, fallback=fallback if fallback is not None else technique.name)


def technique_price_for(character, technique: Technique) -> Restriction | None:
    """The PRICE the character pays to cast ``technique``, or ``None``."""
    hold = character.techniques.hold_for(technique)
    return hold.price if hold is not None and hold.price_id is not None else None


def resolve_price_snippet(character, technique: Technique) -> str | None:
    """The cast-narration clause for the caster's price: authored line, else its name."""
    price = technique_price_for(character, technique)
    if price is None:
        return None
    return price.cast_narration or price.name


def seed_motif_from_gift_resonance(sheet: CharacterSheet, resonance: Resonance) -> MotifResonance:
    """Ensure ``sheet``'s Motif carries ``resonance`` as a gift resonance (idempotent).

    ``MotifResonance.is_from_gift`` documents that gift resonances are auto-populated,
    but nothing did it; without a Motif no ``SignatureMotifBonus`` ever qualifies
    (``SignatureMotifBonus.qualifies_for``). Called at CG finalize (#4099).
    """
    from world.magic.models import Motif, MotifResonance  # noqa: PLC0415

    with transaction.atomic():
        motif, _ = Motif.objects.get_or_create(character=sheet)
        motif_resonance, _ = MotifResonance.objects.get_or_create(
            motif=motif, resonance=resonance, defaults={"is_from_gift": True}
        )
    return motif_resonance
