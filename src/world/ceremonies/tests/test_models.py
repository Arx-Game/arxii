"""Model tests for the ceremonies framework (#2289)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.ceremonies.constants import CeremonyStatus
from world.ceremonies.factories import CeremonyFactory
from world.ceremonies.models import get_ceremony_config


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
