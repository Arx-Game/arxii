"""Handler for the reply parent edge (#3787): which interaction each one answered.

``InteractionReply`` is sparse - one row per reply, absent for every other row - so
each interaction's edge is a list of zero or one rows. Read through
``Interaction.reply_link_handler`` rather than a bare ``Prefetch`` with a `to_attr`
kwarg: that spelling silently stops running the second time an instance is warm
under the identity map (ADR-0263, #3673) - the exact staleness
``InteractionReplyHandler`` exists to avoid, mirroring
``world.journals.handlers.IntroductionsHandler`` and
``world.companions.handlers.CompanionOrderHandler``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from evennia_extensions.handlers import CachedRowsHandler
from world.scenes.models import InteractionReply

if TYPE_CHECKING:
    from django.db import models


class InteractionReplyHandler(CachedRowsHandler[InteractionReply]):
    """The parent edge for one interaction, if it is a reply - zero or one rows."""

    attname: ClassVar[str] = "reply_link_handler"

    def load(self) -> list[InteractionReply]:
        return list(InteractionReply.objects.filter(interaction=self.parent)[:1])

    @classmethod
    def rows_for(cls, parents: list[models.Model]) -> dict[int, list[InteractionReply]]:
        """One query for every reply edge across ``parents``, bucketed by interaction."""
        grouped: dict[int, list[InteractionReply]] = defaultdict(list)
        rows = InteractionReply.objects.filter(interaction_id__in=[p.pk for p in parents])
        for row in rows:
            grouped[row.interaction_id].append(row)
        return grouped
