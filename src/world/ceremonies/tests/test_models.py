"""Model tests for the ceremonies framework (#2289)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.ceremonies.constants import CeremonyStatus, SeanceOfferStatus
from world.ceremonies.factories import (
    CeremonyFactory,
    CeremonyHonoreeFactory,
    SeanceManifestationOfferFactory,
)
from world.ceremonies.models import SeanceManifestationOffer, get_ceremony_config


class CeremonyModelTests(TestCase):
    def test_one_open_ceremony_per_location(self) -> None:
        first = CeremonyFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            CeremonyFactory(location=first.location)

    def test_second_ceremony_allowed_once_first_completes(self) -> None:
        first = CeremonyFactory()
        first.status = CeremonyStatus.COMPLETED
        first.save(update_fields=["status"])
        second = CeremonyFactory(location=first.location)
        self.assertEqual(second.status, CeremonyStatus.OPEN)

    def test_is_twisted_property(self) -> None:
        from world.worship.factories import WorshippedBeingFactory

        open_rite = CeremonyFactory()
        self.assertFalse(open_rite.is_twisted)
        twisted = CeremonyFactory(presented_being=WorshippedBeingFactory())
        self.assertTrue(twisted.is_twisted)

    def test_config_singleton(self) -> None:
        first = get_ceremony_config()
        second = get_ceremony_config()
        self.assertEqual(first.pk, second.pk)


class SeanceManifestationOfferModelTests(TestCase):
    def test_defaults_to_pending(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        offer = SeanceManifestationOfferFactory(
            ceremony_honoree=CeremonyHonoreeFactory(honoree_sheet=CharacterSheetFactory())
        )
        self.assertEqual(offer.status, SeanceOfferStatus.PENDING)
        self.assertIsNone(offer.responded_at)

    def test_one_offer_per_honoree(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        honoree = CeremonyHonoreeFactory(honoree_sheet=CharacterSheetFactory())
        SeanceManifestationOffer.objects.create(ceremony_honoree=honoree)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SeanceManifestationOffer.objects.create(ceremony_honoree=honoree)
