"""Handlers for Character access to Companion rows (#672)."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from evennia_extensions.handlers import CachedRowsHandler
from world.companions.models import Companion, CompanionOrder

if TYPE_CHECKING:
    from django.db import models

    from typeclasses.characters import Character


class CharacterCompanionHandler:
    """Handler for a character's bonded Companion rows.

    Mirrors the CharacterThreadHandler/CharacterConditionHandler cached-property
    handler pattern (world/magic/handlers.py, world/conditions/handlers.py).
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    def active(self) -> list[Companion]:
        """This character's currently-bonded (unreleased) companions.

        Returns [] gracefully when the character has no sheet_data (mirrors
        the existing self.character_sheet guard pattern used
        throughout typeclasses/characters.py) — e.g. a CompanionObject or a
        GM/Staff character has no companions of its own.
        """
        sheet = self.character.character_sheet
        if sheet is None:
            return []
        return list(
            Companion.objects.filter(owner=sheet, released_at__isnull=True).select_related(
                "objectdb"
            )
        )


class CompanionOrderHandler(CachedRowsHandler[CompanionOrder]):
    """Current encounter-scoped companion directives, ordered by companion."""

    attname: ClassVar[str] = "companion_orders_cached"

    def load(self) -> list[CompanionOrder]:
        encounter = self.parent
        return list(
            CompanionOrder.objects.filter(
                encounter=encounter,
                round_number=encounter.round_number,
            )
            .select_related("companion")
            .order_by("companion_id", "id")
        )

    @classmethod
    def rows_for(cls, parents: list[models.Model]) -> dict[int, list[CompanionOrder]]:
        """Load current-round orders for multiple encounters in one query."""
        grouped: dict[int, list[CompanionOrder]] = defaultdict(list)
        encounter_ids = [parent.pk for parent in parents if parent.pk]
        rows = CompanionOrder.objects.filter(encounter_id__in=encounter_ids).select_related(
            "companion", "encounter"
        )
        for row in rows:
            if row.encounter_id is not None and row.round_number == row.encounter.round_number:
                grouped[row.encounter_id].append(row)
        return dict(grouped)
