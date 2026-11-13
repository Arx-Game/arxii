"""How a missive's correspondents read to one character (#3289).

One rule for every surface that names them: the telnet list and ``read``, the REST list,
and the send/reply confirmations. A mask stays a mask; a name the viewer typed stays the
name it typed.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from world.messengers.services import sent_by
from world.scenes.persona_display import build_persona_display_map, resolve_display_for_viewer

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.messengers.models import Missive
    from world.scenes.models import Persona


# persona pk -> (display_name, is_discovered, reveal_allowed), from build_persona_display_map.
DisplayMap = dict[int, tuple[str, bool, bool]]


def display_map_for(sheet: CharacterSheet, missives: Iterable[Missive]) -> DisplayMap:
    """Every correspondent on these missives as this character reads them, in one batch.

    The list surfaces (telnet ``missive``, the REST page) build this once per page so a
    page of masked writers costs one discovery query, not one per row.
    """
    personas = [
        persona
        for missive in missives
        for persona in (missive.sender_persona, missive.recipient_persona)
    ]
    return build_persona_display_map(personas, viewer_sheet=sheet)


def shown_name(persona: Persona, sheet: CharacterSheet, names: DisplayMap | None = None) -> str:
    """How ``persona`` reads to this character: real for its own faces and named faces, the
    discovered name or the composed description for a mask it has not seen through.

    ``names`` is a ``display_map_for`` batch over the same viewer; the single-persona
    resolver is the same rule for one face.
    """
    if names is not None and persona.pk in names:
        return names[persona.pk][0]
    return resolve_display_for_viewer(persona, viewer_sheet=sheet)[0]


def missive_correspondents(
    sheet: CharacterSheet, missive: Missive, names: DisplayMap | None = None
) -> tuple[str, str]:
    """``(from, to)`` names of a missive as this character reads them.

    The sender always reads through the viewer's eyes. The recipient reads as addressed
    when this character wrote a fresh letter (it typed that name), and through its eyes
    otherwise: a reply to a masked writer must not name what the mask hides.
    """
    recipient = missive.recipient_persona
    if sent_by(sheet, missive) and missive.in_reply_to_id is None:
        to_name = recipient.name
    else:
        to_name = shown_name(recipient, sheet, names)
    return shown_name(missive.sender_persona, sheet, names), to_name
