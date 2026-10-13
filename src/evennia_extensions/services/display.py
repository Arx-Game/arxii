"""The one writer of an object's look description (#4329).

An object's description lives in ``ObjectDisplayData.permanent_description``:
``look`` reads it for a room, a character, an item and an exit alike (through the
data handler's ``get_display_description()``). Evennia's ``desc`` Attribute is a
second store that nothing renders, so anything that sets a description comes here
instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.models import ObjectDisplayData
from server.conf.mush_markup import normalize_mush_markup

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def set_permanent_description(obj: ObjectDB, description: str) -> None:
    """Set ``obj``'s permanent description, the text ``look`` shows.

    Takes any object, since every kind has a description. ``%r``/``%t`` markup is
    normalized to real line breaks and tabs, the convention telnet input already
    applies, so text typed on the web and text typed on telnet store the same way.
    """
    display, _ = ObjectDisplayData.objects.get_or_create(object=obj)
    display.permanent_description = normalize_mush_markup(description)
    display.save(update_fields=["permanent_description"])
