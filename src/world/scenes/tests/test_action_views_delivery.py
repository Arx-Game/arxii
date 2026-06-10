"""API surface for action delivery (#903)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionDelivery
from world.scenes.factories import SceneFactory


class ActionRequestDeliveryAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

        cls.target_character = CharacterFactory()
        cls.target_identity = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.primary_persona

        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def _payload(self, **extra) -> dict:
        return {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona": self.target_persona.pk,
            "action_key": "seduce",
            **extra,
        }

    def test_create_with_whisper_delivery(self) -> None:
        response = self.client.post(
            reverse("sceneactionrequest-list"),
            self._payload(delivery=ActionDelivery.WHISPER.value),
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["delivery"] == ActionDelivery.WHISPER

    def test_create_without_delivery_stores_blank(self) -> None:
        response = self.client.post(
            reverse("sceneactionrequest-list"), self._payload(), format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["delivery"] == ""

    def test_table_talk_without_place_is_400(self) -> None:
        response = self.client.post(
            reverse("sceneactionrequest-list"),
            self._payload(delivery=ActionDelivery.TABLE_TALK.value),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_delivery_choice_is_400(self) -> None:
        response = self.client.post(
            reverse("sceneactionrequest-list"),
            self._payload(delivery="shout_from_rooftops"),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_delivery_receiver_is_400(self) -> None:
        response = self.client.post(
            reverse("sceneactionrequest-list"),
            self._payload(
                delivery=ActionDelivery.WHISPER.value,
                delivery_receiver_ids=[999999],
            ),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
