"""REST surface for reaction windows (#904)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_services import open_reaction_window, register_reaction_kind
from world.scenes.tests.test_reaction_windows import _binary_kind


def _account_with_persona(scene=None):
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    if scene is not None:
        SceneParticipationFactory(scene=scene, account=account)
    return account, roster_entry.character_sheet.primary_persona


class ReactionWindowAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.writer_account, cls.writer = _account_with_persona(cls.scene)
        cls.reactor_account, cls.reactor = _account_with_persona(cls.scene)
        cls.interaction = InteractionFactory(persona=cls.writer, scene=cls.scene)

    def setUp(self) -> None:
        from world.scenes.reaction_services import _KIND_REGISTRY

        original = _KIND_REGISTRY.get(ReactionWindowKind.ENTRANCE)
        if original is not None:
            self.addCleanup(register_reaction_kind, ReactionWindowKind.ENTRANCE, original)
        register_reaction_kind(ReactionWindowKind.ENTRANCE, _binary_kind())
        self.window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )
        self.url = reverse("reactionwindow-react", kwargs={"pk": self.window.pk})

    def test_react_happy_path(self) -> None:
        self.client.force_authenticate(user=self.reactor_account)
        response = self.client.post(
            self.url, {"persona_id": self.reactor.pk, "choice": "acclaim"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["choice"] == "acclaim"

    def test_react_with_unowned_persona_is_400(self) -> None:
        self.client.force_authenticate(user=self.reactor_account)
        response = self.client.post(
            self.url, {"persona_id": self.writer.pk, "choice": "acclaim"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_react_is_400(self) -> None:
        self.client.force_authenticate(user=self.reactor_account)
        self.client.post(
            self.url, {"persona_id": self.reactor.pk, "choice": "acclaim"}, format="json"
        )
        response = self.client.post(
            self.url, {"persona_id": self.reactor.pk, "choice": "disdain"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_interaction_payload_carries_window(self) -> None:
        self.client.force_authenticate(user=self.reactor_account)
        self.client.post(
            self.url, {"persona_id": self.reactor.pk, "choice": "acclaim"}, format="json"
        )
        response = self.client.get(
            reverse("interaction-detail", kwargs={"pk": self.interaction.pk})
        )
        assert response.status_code == status.HTTP_200_OK
        windows = response.data["reaction_windows"]
        assert len(windows) == 1
        payload = windows[0]
        assert payload["kind"] == ReactionWindowKind.ENTRANCE
        assert payload["is_open"] is True
        assert {c["slug"] for c in payload["choices"]} == {"acclaim", "disdain"}
        assert payload["counts"] == {"acclaim": 1}
        assert payload["my_reaction"] == "acclaim"
        assert payload["reactions"][0]["persona_id"] == self.reactor.pk

    def test_window_payload_my_reaction_null_for_other_viewer(self) -> None:
        self.client.force_authenticate(user=self.reactor_account)
        self.client.post(
            self.url, {"persona_id": self.reactor.pk, "choice": "acclaim"}, format="json"
        )
        self.client.force_authenticate(user=self.writer_account)
        response = self.client.get(
            reverse("interaction-detail", kwargs={"pk": self.interaction.pk})
        )
        assert response.data["reaction_windows"][0]["my_reaction"] is None
        assert response.data["reaction_windows"][0]["counts"] == {"acclaim": 1}
