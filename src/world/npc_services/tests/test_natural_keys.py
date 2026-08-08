"""Natural-key round-trips for the MISSION-offer content models (#3056)."""

from django.test import TestCase

from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.models import MissionOfferDetails, NPCServiceOffer


class NPCServiceOfferNaturalKeyTests(TestCase):
    """(role, label) is the enforced identity (unique_offer_role_label)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = NPCRoleFactory(name="Thread Warden")
        cls.offer = NPCServiceOfferFactory(
            role=cls.role, kind=OfferKind.MISSION, label="A thread that wants weaving"
        )

    def test_natural_key_flattens_role_name_and_label(self) -> None:
        assert self.offer.natural_key() == ("Thread Warden", "A thread that wants weaving")

    def test_get_by_natural_key_round_trips(self) -> None:
        found = NPCServiceOffer.objects.get_by_natural_key(
            "Thread Warden", "A thread that wants weaving"
        )
        assert found == self.offer

    def test_get_by_natural_key_miss_raises(self) -> None:
        with self.assertRaises(NPCServiceOffer.DoesNotExist):
            NPCServiceOffer.objects.get_by_natural_key("Thread Warden", "No such offer")


class MissionOfferDetailsNaturalKeyTests(TestCase):
    """The O2O offer IS the identity; its FK key flattens into the tuple."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.details = MissionOfferDetailsFactory(
            offer__role__name="Thread Warden",
            offer__label="A thread that wants weaving",
        )

    def test_natural_key_flattens_offer_key(self) -> None:
        assert self.details.natural_key() == ("Thread Warden", "A thread that wants weaving")

    def test_get_by_natural_key_round_trips(self) -> None:
        found = MissionOfferDetails.objects.get_by_natural_key(
            "Thread Warden", "A thread that wants weaving"
        )
        assert found == self.details
