"""Spread a Tale API endpoints (#745 Phase 1b — PersonaViewSet actions)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory, SceneFactory, SceneParticipationFactory
from world.societies.factories import (
    LegendEntryFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)


class SpreadEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        character = CharacterFactory()
        roster_entry = RosterEntryFactory(character_sheet__character=character)
        player_data = PlayerDataFactory(account=cls.account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        identity = CharacterSheetFactory(character=character)
        cls.persona = identity.primary_persona

        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.account)
        society = SocietyFactory()
        org = OrganizationFactory(society=society)
        OrganizationMembershipFactory(persona=cls.persona, organization=org)
        cls.deed = LegendEntryFactory(persona=PersonaFactory(), base_value=50)
        cls.deed.societies_aware.add(society)
        ActionPointPool.get_or_create_for_character(character)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_spreadable_deeds_lists_known_deed(self) -> None:
        url = reverse("persona-spreadable-deeds", args=[self.persona.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(self.deed.pk, [d["id"] for d in resp.data])

    def test_spread_resolves(self) -> None:
        url = reverse("persona-spread", args=[self.persona.pk])
        resp = self.client.post(
            url,
            {"scene": self.scene.pk, "deed": self.deed.pk, "pose_text": "A song."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data["resolved"])
        self.assertIn("band", resp.data)

    def test_spread_unowned_persona_forbidden(self) -> None:
        other = PersonaFactory()
        url = reverse("persona-spread", args=[other.pk])
        resp = self.client.post(url, {"scene": self.scene.pk, "deed": self.deed.pk}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
