"""Rows a sheet owns in the journals app, behind handlers (ADR-0278).

``IntroductionsHandler`` is the CG Introductions (#3621): the white journals of a kind
other than a plain entry, in the order written. Hung off ``CharacterSheet.introductions``;
cleared by any entry save or delete through ``JournalEntry.related_cache_fields``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from evennia_extensions.handlers import CachedRowsHandler
from world.journals.constants import JournalKind
from world.journals.models import JournalEntry

if TYPE_CHECKING:
    from django.db import models


class IntroductionsHandler(CachedRowsHandler[JournalEntry]):
    """The Introductions a character wrote, oldest first."""

    attname: ClassVar[str] = "introductions"

    def load(self) -> list[JournalEntry]:
        return list(
            JournalEntry.objects.filter(author=self.parent)
            .exclude(kind=JournalKind.ENTRY)
            .order_by("created_at", "id")
        )

    @classmethod
    def rows_for(cls, parents: list[models.Model]) -> dict[int, list[JournalEntry]]:
        """One query for every Introduction across ``parents``, bucketed by sheet."""
        grouped: dict[int, list[JournalEntry]] = defaultdict(list)
        rows = (
            JournalEntry.objects.filter(author_id__in=[parent.pk for parent in parents])
            .exclude(kind=JournalKind.ENTRY)
            .order_by("created_at", "id")
        )
        for entry in rows:
            grouped[entry.author_id].append(entry)
        return grouped
