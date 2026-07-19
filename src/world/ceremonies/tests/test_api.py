"""Ceremony API tests (#2289) — including the twisted-rite leak rule."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.factories import CeremonyFactory, CeremonyTypeFactory
from world.ceremonies.serializers import CeremonySerializer
from world.ceremonies.services import open_ceremony
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipDeclaration


def _retired_honoree_with_offer():
    CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
    officiant_sheet = CharacterSheetFactory()
    CharacterVitalsFactory(character_sheet=officiant_sheet)
    being = WorshippedBeingFactory()
    WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)

    sheet = CharacterSheetFactory()
    CharacterVitalsFactory(
        character_sheet=sheet, life_state=CharacterLifeState.DEAD, retired_at=timezone.now()
    )
    player_data = PlayerDataFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data=player_data)

    ceremony = open_ceremony(
        officiant_persona=officiant_sheet.primary_persona,
        type_key=CeremonyTypeKey.SEANCE,
        honoree_sheets=[sheet],
        location_profile=RoomProfileFactory(),
    )
    offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer
    return offer, player_data.account


class SeanceOfferApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_list_returns_own_pending_offers_only(self) -> None:
        offer, account = _retired_honoree_with_offer()
        stranger = AccountFactory()

        self.client.force_authenticate(user=stranger)
        stranger_response = self.client.get("/api/ceremonies/seance-offers/")
        self.assertEqual(stranger_response.status_code, 200)
        self.assertEqual(stranger_response.data, [])

        self.client.force_authenticate(user=account)
        response = self.client.get("/api/ceremonies/seance-offers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [offer.pk])

    def test_accept_dispatches_the_action(self) -> None:
        offer, account = _retired_honoree_with_offer()
        self.client.force_authenticate(user=account)

        response = self.client.post(f"/api/ceremonies/seance-offers/{offer.pk}/accept/")

        self.assertEqual(response.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, "accepted")


class CeremonyApiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_serializer_never_exposes_true_being_of_twisted_rite(self) -> None:
        dark = WorshippedBeingFactory(name="The Hidden Flame Test")
        public = WorshippedBeingFactory(name="The Public Face Test")
        twisted = CeremonyFactory(being=dark, presented_being=public)
        payload = CeremonySerializer(twisted).data
        self.assertEqual(payload["presented_being_name"], public.name)
        self.assertNotIn(dark.name, str(payload))
        self.assertNotIn("being_id", payload)

    def test_list_filters_by_status(self) -> None:
        CeremonyFactory()
        response = self.client.get("/api/ceremonies/ceremonies/", {"status": "open"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_beings_catalog_lists_active_only(self) -> None:
        WorshippedBeingFactory(name="Active God Test")
        WorshippedBeingFactory(name="Retired God Test", is_active=False)
        response = self.client.get("/api/worship/beings/")
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Active God Test", names)
        self.assertNotIn("Retired God Test", names)
