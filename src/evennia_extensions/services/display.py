"""The shared writer of a room's, object's or exit's look description (#4329).

Their description lives in ``ObjectDisplayData.permanent_description``, which
``look`` reads through the data handler's ``get_display_description()``. (A
character's lives on its sheet, an item's on its ``ItemInstance``.) Evennia's ``desc``
Attribute is a second store that nothing renders, so code that sets one of these
descriptions comes here instead.
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
    display.save(update_fields=["permanent_description", "updated_date"])
