"""Entry-flourish self-grant offer (#1140).

Poll-able offer created when a character's Entrance social action succeeds.
The entrant picks one of their own claimed resonances to broadcast; the pick
resolves through ``create_entry_flourish`` (actor self-grant). Mirrors the
Audere offer pattern (``world/magic/audere.py``) but is a self-grant, NOT a
reaction window (which is peer-only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models, transaction
from evennia.utils.idmapper.models import SharedMemoryModel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Resonance
    from world.scenes.models import Scene


class PendingEntryFlourishOffer(SharedMemoryModel):
    """A poll-able offer awaiting the entrant's resonance pick (#1140)."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="entry_flourish_offers",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entry_flourish_offers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                name="one_pending_entry_flourish_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"PendingEntryFlourishOffer(sheet={self.character_sheet_id}, scene={self.scene_id})"


def maybe_create_entry_flourish_offer(
    character: ObjectDB, scene: Scene | None
) -> PendingEntryFlourishOffer | None:
    """Create/refresh the entrant's pending flourish offer, or None if not applicable."""
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.magic.models import CharacterResonance  # noqa: PLC0415
    from world.magic.models.endorsement import EntryFlourishRecord  # noqa: PLC0415

    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return None
    if (
        scene is not None
        and EntryFlourishRecord.objects.filter(character_sheet=sheet, scene=scene).exists()
    ):
        return None  # already flourished this scene
    if not CharacterResonance.objects.filter(character_sheet=sheet).exists():
        return None  # nothing claimed to broadcast
    offer, _ = PendingEntryFlourishOffer.objects.update_or_create(
        character_sheet=sheet, defaults={"scene": scene}
    )
    return offer


@dataclass
class EntryFlourishResult:
    """Result of resolving an entry-flourish offer."""

    resonance_id: int
    resonance_name: str
    granted_amount: int
    scene_id: int | None


def resolve_entry_flourish_offer(
    offer: PendingEntryFlourishOffer, *, resonance: Resonance
) -> EntryFlourishResult:
    """Two-phase resolve: staleness check outside the txn; locked grant inside.

    Phase 1 (outside transaction): validate resonance is claimed by the sheet.
    If unclaimed → delete offer + EntryFlourishOfferStaleError.

    Phase 2 (inside transaction.atomic with select_for_update): re-fetch offer,
    call create_entry_flourish, delete locked offer row, return EntryFlourishResult.
    """
    from world.magic.exceptions import (  # noqa: PLC0415
        EntryFlourishOfferNotFoundError,
        EntryFlourishOfferStaleError,
    )
    from world.magic.models import CharacterResonance  # noqa: PLC0415
    from world.magic.services.gain import create_entry_flourish  # noqa: PLC0415

    sheet = offer.character_sheet
    scene = offer.scene
    if not CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists():
        offer.delete()
        raise EntryFlourishOfferStaleError

    with transaction.atomic():
        locked = PendingEntryFlourishOffer.objects.select_for_update().filter(pk=offer.pk).first()
        if locked is None:
            raise EntryFlourishOfferNotFoundError
        record = create_entry_flourish(sheet, resonance, scene=scene)
        locked.delete()

    return EntryFlourishResult(
        resonance_id=resonance.pk,
        resonance_name=resonance.name,
        granted_amount=record.granted_amount,
        scene_id=scene.pk if scene is not None else None,
    )
