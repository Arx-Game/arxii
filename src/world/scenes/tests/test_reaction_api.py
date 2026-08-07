"""REST surface for reaction windows (#904)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Block, Mute
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


class ReactionWindowBlockMuteTests(APITestCase):
    """#2996 Decision 2 — account block/mute at the kudos/reaction-window seam.

    Write path (``react_to_window``) is unmodified — a reactor's own create response never
    changes. Suppression is entirely on reads of ``reaction_windows`` (``get_reaction_windows``
    in ``interaction_serializers.py``): block only suppresses a reactor from the pose's own
    author (the reaction's "target") reading it; mute suppresses a reactor from every viewer's
    own read who holds the mute, regardless of whose pose it is.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.writer_account, cls.writer = _account_with_persona(cls.scene)
        cls.reactor_account, cls.reactor = _account_with_persona(cls.scene)
        cls.viewer_account, cls.viewer_persona = _account_with_persona(cls.scene)
        cls.interaction = InteractionFactory(persona=cls.writer, scene=cls.scene)
        cls.writer_player = PlayerData.objects.get(account=cls.writer_account)
        cls.reactor_player = PlayerData.objects.get(account=cls.reactor_account)
        cls.viewer_player = PlayerData.objects.get(account=cls.viewer_account)

    def setUp(self) -> None:
        from world.scenes.reaction_services import _KIND_REGISTRY

        original = _KIND_REGISTRY.get(ReactionWindowKind.ENTRANCE)
        if original is not None:
            self.addCleanup(register_reaction_kind, ReactionWindowKind.ENTRANCE, original)
        register_reaction_kind(ReactionWindowKind.ENTRANCE, _binary_kind())
        self.window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )
        self.react_url = reverse("reactionwindow-react", kwargs={"pk": self.window.pk})
        self.detail_url = reverse("interaction-detail", kwargs={"pk": self.interaction.pk})

    def _react_as_reactor(self):
        self.client.force_authenticate(user=self.reactor_account)
        response = self.client.post(
            self.react_url, {"persona_id": self.reactor.pk, "choice": "acclaim"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        return response

    def _reactions_for(self, account):
        self.client.force_authenticate(user=account)
        response = self.client.get(self.detail_url)
        assert response.status_code == status.HTTP_200_OK
        return response.data["reaction_windows"][0]["reactions"]

    def test_block_hides_reactor_from_poses_own_authors_read(self) -> None:
        Block.objects.create(
            owner=self.writer_player,
            blocked_player=self.reactor_player,
            account_level=True,
        )
        self._react_as_reactor()

        reactions = self._reactions_for(self.writer_account)
        assert all(r["persona_id"] != self.reactor.pk for r in reactions)

    def test_block_does_not_affect_a_different_viewers_read(self) -> None:
        Block.objects.create(
            owner=self.writer_player,
            blocked_player=self.reactor_player,
            account_level=True,
        )
        self._react_as_reactor()

        reactions = self._reactions_for(self.viewer_account)
        assert any(r["persona_id"] == self.reactor.pk for r in reactions)

    def test_block_does_not_affect_the_reactors_own_write(self) -> None:
        """Leak check: reacting while blocked returns the normal create response."""
        Block.objects.create(
            owner=self.writer_player,
            blocked_player=self.reactor_player,
            account_level=True,
        )
        response = self._react_as_reactor()
        assert response.data["choice"] == "acclaim"
        assert response.data["persona_id"] == self.reactor.pk

    def test_mute_hides_reactor_from_the_muters_own_read_only(self) -> None:
        Mute.objects.create(
            owner=self.viewer_player,
            muted_persona=PersonaFactory(),
            muted_player=self.reactor_player,
            account_level=True,
        )
        self._react_as_reactor()

        muted_viewer_reactions = self._reactions_for(self.viewer_account)
        assert all(r["persona_id"] != self.reactor.pk for r in muted_viewer_reactions)

        # The pose author (not the muter) still sees the reaction normally.
        writer_reactions = self._reactions_for(self.writer_account)
        assert any(r["persona_id"] == self.reactor.pk for r in writer_reactions)

    def test_mute_does_not_affect_the_reactors_own_write(self) -> None:
        Mute.objects.create(
            owner=self.viewer_player,
            muted_persona=PersonaFactory(),
            muted_player=self.reactor_player,
            account_level=True,
        )
        response = self._react_as_reactor()
        assert response.data["choice"] == "acclaim"
        assert response.data["persona_id"] == self.reactor.pk
