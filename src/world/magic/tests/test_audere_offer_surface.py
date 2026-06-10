"""Tests for the PendingAudereOffer surface (#873): model, services, hook."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.audere import PendingAudereOffer


class PendingAudereOfferModelTests(TestCase):
    """Model shape: one pending offer per character sheet."""

    def test_unique_per_character_sheet(self) -> None:
        sheet = CharacterSheetFactory()
        PendingAudereOffer.objects.create(
            character_sheet=sheet, fired_intensity=20, soulfray_stage_order=2
        )
        offer, created = PendingAudereOffer.objects.update_or_create(
            character_sheet=sheet,
            defaults={"fired_intensity": 25, "soulfray_stage_order": 3},
        )
        assert created is False
        assert offer.fired_intensity == 25
        assert PendingAudereOffer.objects.filter(character_sheet=sheet).count() == 1
