from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    PoseEndorsementFactory,
    ResonanceFactory,
    SceneEntryEndorsementFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PoseKind,
    ScenePrivacyMode,
)
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    PlaceFactory,
    SceneFactory,
)
from world.scenes.models import (
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionTargetPersona,
    SceneParticipation,
)


class InteractionViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Build the full identity chain: Account -> PlayerData -> RosterTenure
        # -> RosterEntry -> CharacterSheet -> Persona (PRIMARY, auto-created
        # by CharacterSheetFactory; no CharacterIdentity model anymore —
        # merged into CharacterSheet in the 2026-04 refactor)
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

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character_sheet__character=cls.other_character)
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            player_data=cls.other_player_data,
            roster_entry=cls.other_roster_entry,
        )
        cls.other_identity = CharacterSheetFactory(character=cls.other_character)
        cls.other_persona = cls.other_identity.primary_persona

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_list_interactions(self) -> None:
        """Authenticated users can list interactions."""
        InteractionFactory(persona=self.persona)
        InteractionFactory(persona=self.other_persona)
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_by_persona(self) -> None:
        """Interactions can be filtered by persona."""
        InteractionFactory(persona=self.persona)
        InteractionFactory(persona=self.other_persona)
        url = reverse("interaction-list")
        response = self.client.get(url, {"persona": self.persona.pk})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["persona"]["name"] == self.persona.name

    def test_toggle_favorite_create_and_remove(self) -> None:
        """Posting to favorites creates, posting again removes."""
        interaction = InteractionFactory(persona=self.persona)
        url = reverse("interactionfavorite-list")

        # Create favorite
        response = self.client.post(url, {"interaction": interaction.pk}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert InteractionFavorite.objects.filter(
            interaction=interaction,
            roster_entry=self.roster_entry,
        ).exists()

        # Toggle off
        response = self.client.post(url, {"interaction": interaction.pk}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert not InteractionFavorite.objects.filter(
            interaction=interaction,
            roster_entry=self.roster_entry,
        ).exists()

    def test_delete_own_recent_interaction(self) -> None:
        """Writer can delete their own recent interaction."""
        interaction = InteractionFactory(persona=self.persona)
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    @suppress_permission_errors
    def test_cannot_delete_others_interaction(self) -> None:
        """Non-writer cannot delete another user's interaction.

        With privacy filtering, if the interaction is not visible to the user
        (not writer, not receiver, not in a public scene), it returns 404
        rather than 403 to avoid leaking existence. If the interaction IS
        visible (e.g. via receiver membership), the permission check returns 403.
        """
        # Interaction without receiver membership - returns 404 (not in queryset)
        interaction = InteractionFactory(
            persona=self.other_persona,
            mode="whisper",
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Interaction with receiver membership - returns 403 (visible but not writer)
        visible_interaction = InteractionFactory(persona=self.other_persona)
        InteractionReceiverFactory(
            interaction=visible_interaction,
            persona=self.persona,
        )
        url = reverse("interaction-detail", kwargs={"pk": visible_interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_mark_interaction_as_very_private(self) -> None:
        """Receiver or writer can mark interaction as very_private."""
        interaction = InteractionFactory(persona=self.persona)
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.persona,
        )
        url = reverse("interaction-mark-private", kwargs={"pk": interaction.pk})
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_retrieve_interaction_detail_includes_receivers(self) -> None:
        """Detail view includes receiver data."""
        interaction = InteractionFactory(persona=self.persona)
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.other_persona,
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "receivers" in response.data
        assert len(response.data["receivers"]) == 1


class InteractionFeedPrivacyTests(APITestCase):
    """Receiver-scoped interactions must never leak through scene-level visibility.

    Regression for the public-scene leak: whispers and table talk in a PUBLIC
    scene were readable by everyone in the persisted feed (list + retrieve),
    even though the real-time push only went to writer + receivers.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        def build_account():
            account = AccountFactory()
            character = CharacterFactory()
            roster_entry = RosterEntryFactory(character_sheet__character=character)
            player_data = PlayerDataFactory(account=account)
            RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
            return account, roster_entry.character_sheet.primary_persona

        cls.writer_account, cls.writer_persona = build_account()
        cls.receiver_account, cls.receiver_persona = build_account()
        cls.outsider_account, cls.outsider_persona = build_account()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.public_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.pose = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.POSE,
            scene=cls.public_scene,
        )
        cls.whisper = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.WHISPER,
            scene=cls.public_scene,
        )
        InteractionReceiverFactory(interaction=cls.whisper, persona=cls.receiver_persona)
        cls.place = PlaceFactory()
        cls.table_talk = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.SAY,
            scene=cls.public_scene,
            place=cls.place,
        )
        InteractionReceiverFactory(interaction=cls.table_talk, persona=cls.receiver_persona)

    def _result_ids(self, response) -> set[int]:
        return {row["id"] for row in response.data["results"]}

    def test_outsider_list_excludes_whisper_and_table_talk(self) -> None:
        self.client.force_authenticate(user=self.outsider_account)
        response = self.client.get(reverse("interaction-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = self._result_ids(response)
        assert self.pose.pk in ids
        assert self.whisper.pk not in ids
        assert self.table_talk.pk not in ids

    def test_outsider_cannot_retrieve_whisper(self) -> None:
        self.client.force_authenticate(user=self.outsider_account)
        url = reverse("interaction-detail", kwargs={"pk": self.whisper.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_receiver_list_includes_whisper_and_table_talk(self) -> None:
        self.client.force_authenticate(user=self.receiver_account)
        response = self.client.get(reverse("interaction-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = self._result_ids(response)
        assert self.whisper.pk in ids
        assert self.table_talk.pk in ids

    def test_writer_list_includes_own_whisper(self) -> None:
        self.client.force_authenticate(user=self.writer_account)
        response = self.client.get(reverse("interaction-list"))
        assert response.status_code == status.HTTP_200_OK
        assert self.whisper.pk in self._result_ids(response)

    def test_staff_sees_whisper_but_not_very_private(self) -> None:
        very_private = InteractionFactory(
            persona=self.writer_persona,
            mode=InteractionMode.WHISPER,
            scene=self.public_scene,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        InteractionReceiverFactory(interaction=very_private, persona=self.receiver_persona)
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(reverse("interaction-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = self._result_ids(response)
        assert self.whisper.pk in ids
        assert very_private.pk not in ids

    def test_no_persona_feed_excludes_whisper_and_table_talk(self) -> None:
        """An account with no personas gets the public-only branch, minus receiver-scoped rows."""
        bare_account = AccountFactory()
        self.client.force_authenticate(user=bare_account)
        response = self.client.get(reverse("interaction-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = self._result_ids(response)
        assert self.pose.pk in ids
        assert self.whisper.pk not in ids
        assert self.table_talk.pk not in ids


class PoseSubmitViewTests(APITestCase):
    """View-layer integration tests for the submit_pose endpoint.

    Uses setUpTestData for the identity chain and setUp for per-test flush.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Flush the idmapper BEFORE any factory call: shard-ordered CI runs leave
        # cached ObjectDB instances whose __dict__ carries a DbHolder (.db/.ndb),
        # which breaks the TestData descriptor's deepcopy on first access.
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
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

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.other_character,
        )
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            player_data=cls.other_player_data,
            roster_entry=cls.other_roster_entry,
        )
        cls.other_identity = CharacterSheetFactory(character=cls.other_character)
        cls.other_persona = cls.other_identity.primary_persona

    def setUp(self) -> None:
        # Flush all SharedMemoryModel caches to prevent identity-map contamination
        # across tests when SQLite recycles PKs after per-test transaction rollback.
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        # Room + location wiring stays instance-level (after the TestData deepcopy)
        # so the un-deepcopyable DbHolder a Room can acquire (.ndb via active_scene)
        # never enters the class-attribute graph that setUpTestData deepcopies.
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = self.room
        self.client.force_authenticate(user=self.account)
        self.url = reverse("interaction-submit-pose")
        self.base_ts = timezone.now() - timedelta(hours=1)

    def _make_action(self, *, offset_seconds: int) -> Interaction:
        """Create an ACTION interaction at a controlled timestamp."""
        row = InteractionFactory(
            persona=self.persona,
            mode=InteractionMode.ACTION,
        )
        target_ts = self.base_ts + timedelta(seconds=offset_seconds)
        Interaction.objects.filter(pk=row.pk).update(timestamp=target_ts)
        row.timestamp = target_ts
        return row

    def test_submit_pose_auto_links_prior_actions(self) -> None:
        """POST submit-pose without action_link_ids triggers auto-link service."""
        action_a = self._make_action(offset_seconds=1)
        action_b = self._make_action(offset_seconds=2)

        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "A pose."},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        pose_id = response.data["id"]
        linked_action_ids = set(
            InteractionAction.objects.filter(pose_id=pose_id).values_list(
                "action_interaction_id", flat=True
            )
        )
        assert linked_action_ids == {action_a.pk, action_b.pk}

    def test_submit_pose_with_explicit_action_link_ids_skips_auto_link(self) -> None:
        """When action_link_ids is provided, only those links are created (no auto-link)."""
        action_a = self._make_action(offset_seconds=1)
        action_b = self._make_action(offset_seconds=2)  # noqa: F841

        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "content": "A pose with explicit link.",
                "action_link_ids": [action_a.pk],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        pose_id = response.data["id"]
        links = list(InteractionAction.objects.filter(pose_id=pose_id))
        assert len(links) == 1
        assert links[0].action_interaction_id == action_a.pk

    def test_submit_pose_with_empty_action_link_ids_creates_no_links(self) -> None:
        """When action_link_ids is explicitly [] no auto-link and no links are created."""
        self._make_action(offset_seconds=1)

        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "content": "A pose that opts out of linking.",
                "action_link_ids": [],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        pose_id = response.data["id"]
        assert InteractionAction.objects.filter(pose_id=pose_id).count() == 0

    def test_validate_rejects_non_action_interaction_id(self) -> None:
        """action_link_ids containing a non-ACTION interaction id is rejected 400."""
        pose_interaction = InteractionFactory(
            persona=self.persona,
            mode=InteractionMode.POSE,
        )

        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "content": "A pose.",
                "action_link_ids": [pose_interaction.pk],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_rejects_persona_not_owned_by_user(self) -> None:
        """action_link_ids referencing another persona's actions is rejected 400."""
        response = self.client.post(
            self.url,
            {"persona_id": self.other_persona.pk, "content": "A pose."},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_submit_pose_masked_records_worn_face_not_primary(self) -> None:
        """Authorship is the sheet's ACTIVE persona even when the client sends primary (#981).

        The submitted persona_id only selects the acting character — a client
        passing the primary persona while an alt/mask is worn must not unmask
        the disguise in the permanent scene record.
        """
        from world.scenes.factories import PersonaFactory
        from world.scenes.services import set_active_persona

        mask = PersonaFactory(character_sheet=self.identity, name="The Gray Hood")
        set_active_persona(self.identity, mask)

        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "A pose while masked."},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        interaction = Interaction.objects.get(pk=response.data["id"])
        assert interaction.persona_id == mask.pk

    def test_submit_pose_unmasked_records_primary(self) -> None:
        """With no active face set, authorship stays the primary persona."""
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "A bare-faced pose."},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        interaction = Interaction.objects.get(pk=response.data["id"])
        assert interaction.persona_id == self.persona.pk

    def test_submit_pose_creates_interaction_in_scene(self) -> None:
        """Providing scene_id attaches the pose to that scene."""
        scene = SceneFactory()
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "A posed action in a scene.",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["scene"] == scene.pk

    def test_submit_pose_rejects_when_actor_not_in_scenes_room(self) -> None:
        """A located scene rejects a pose from a persona whose character is elsewhere (#2156)."""
        other_room = ObjectDBFactory(
            db_key="Other Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        scene = SceneFactory(location=other_room)
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "A pose from the wrong room.",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not present" in str(response.data["scene_id"][0])

    def test_submit_pose_accepts_when_actor_in_scenes_room(self) -> None:
        """A located scene accepts a pose when the actor's character is co-located (#2156)."""
        scene = SceneFactory(location=self.room)
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "A pose from the right room.",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_submit_pose_skips_colocation_check_for_locationless_scene(self) -> None:
        """A scene with no location (e.g. scene-less RP) never gates on co-location (#2156)."""
        scene = SceneFactory(location=None)
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "A pose in a scene-less location.",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_submit_entry_pose_opens_reaction_window(self) -> None:
        """pose_kind=entry persists and opens a Make-an-Entrance window (#904)."""
        from world.scenes.constants import PoseKind, ReactionWindowKind
        from world.scenes.models import Interaction
        from world.scenes.reaction_models import ReactionWindow

        scene = SceneFactory()
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "sweeps into the hall, cloak billowing.",
                "pose_kind": PoseKind.ENTRY.value,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        interaction = Interaction.objects.get(pk=response.data["id"])
        assert interaction.pose_kind == PoseKind.ENTRY
        window = ReactionWindow.objects.get(interaction=interaction)
        assert window.kind == ReactionWindowKind.ENTRANCE
        assert window.is_open

    def test_submit_standard_pose_opens_no_window(self) -> None:
        from world.scenes.reaction_models import ReactionWindow

        scene = SceneFactory()
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "nods along.",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert not ReactionWindow.objects.filter(interaction_id=response.data["id"]).exists()

    def test_unauthenticated_request_is_rejected(self) -> None:
        """Unauthenticated requests are rejected with 401 or 403."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "A pose."},
            format="json",
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_submit_pose_response_includes_serialized_list_fields(self) -> None:
        """Response payload includes all InteractionListSerializer fields.

        This exercises the cached_* to_attr attributes (cached_receivers,
        cached_target_personas, cached_favorites, cached_reactions) that the
        freshly-created Interaction won't have from get_queryset()'s Prefetch
        pipeline. Without the empty-list assignment in submit_pose, all four
        get_* methods AttributeError here.
        """
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "A fully serialized pose."},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        # Fields populated from cached_receivers / cached_target_personas
        assert "receiver_persona_ids" in data
        assert data["receiver_persona_ids"] == []
        assert "target_persona_ids" in data
        assert data["target_persona_ids"] == []
        # Fields from cached_favorites / cached_reactions
        assert "is_favorited" in data
        assert data["is_favorited"] is False
        assert "reactions" in data
        assert data["reactions"] == []
        # action_links — newly-created pose has no links yet (empty list injected)
        assert "action_links" in data
        assert data["action_links"] == []

    @patch("world.scenes.interaction_services._broadcast_to_location")
    def test_submit_pose_broadcasts_to_scene_clients(self, mock_broadcast) -> None:
        """REST-submitted poses push the same InteractionPayload the WS path sends."""
        scene = SceneFactory()
        resp = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "scene_id": scene.pk, "content": "A pose."},
            format="json",
        )
        assert resp.status_code == 201
        assert mock_broadcast.call_count == 1
        _location, payload = mock_broadcast.call_args.args
        assert payload["id"] == resp.data["id"]
        assert payload["content"] == "A pose."
        assert payload["receiver_persona_ids"] == []

    @patch("world.scenes.interaction_services._broadcast_to_location")
    def test_submit_pose_no_broadcast_on_validation_error(self, mock_broadcast) -> None:
        resp = self.client.post(
            self.url, {"persona_id": self.persona.pk, "content": ""}, format="json"
        )
        assert resp.status_code == 400
        mock_broadcast.assert_not_called()

    def test_submit_pose_rejects_blank_content(self) -> None:
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "   "},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "content" in response.data

    def test_submit_pose_rejects_oversized_content(self) -> None:
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "a" * 10_001},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "content" in response.data

    def test_submit_pose_rejects_null_bytes_in_content(self) -> None:
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "hello\x00world"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "content" in response.data

    def test_submit_pose_rejects_javascript_link_in_content(self) -> None:
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "[click](javascript:void(0))"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "content" in response.data

    def test_submit_pose_accepts_markdown_link_content(self) -> None:
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "[my site](https://example.com)"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_submit_pose_accepts_mention_content(self) -> None:
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "@Alice waves hello"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    @patch("world.scenes.interaction_views.message_location")
    def test_submit_pose_broadcasts_via_message_location(self, mock_message_location) -> None:
        """REST poses reach telnet clients too (#2156) — the same message_location

        call PoseAction.execute makes, so a room-wide raw-text broadcast fires
        regardless of which surface (web/telnet) submitted the pose.
        """
        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "content": "waves at the room."},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert mock_message_location.call_count == 1
        _caller_state, text = mock_message_location.call_args.args
        assert text == "waves at the room."

    def test_submit_pose_creates_scene_participation_for_latecomer(self) -> None:
        """A web pose into a scene the poser has no SceneParticipation row in yet

        enrolls them (#2156) — parity with the WS pose path's
        ``_ensure_scene_participation`` call.
        """
        scene = SceneFactory()
        assert not SceneParticipation.objects.filter(scene=scene, account=self.account).exists()

        response = self.client.post(
            self.url,
            {"persona_id": self.persona.pk, "scene_id": scene.pk, "content": "arrives late."},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert SceneParticipation.objects.filter(scene=scene, account=self.account).exists()

    @patch("world.scenes.interaction_services._broadcast_to_location")
    def test_submit_pose_in_ephemeral_scene_is_not_persisted(self, mock_broadcast) -> None:
        """EPHEMERAL scenes push in real-time but never persist a POSE row (#2156)."""
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)

        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "scene_id": scene.pk,
                "content": "a pose that must not be written to the log.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == {"ephemeral": True}
        assert not Interaction.objects.filter(scene=scene).exists()
        assert mock_broadcast.call_count == 1

    def test_submit_pose_with_target_names_creates_target_rows(self) -> None:
        """target_names resolves co-located characters into InteractionTargetPersona

        rows (#2156) — the REST equivalent of the WS ``@Name``-prefix parse.
        """
        target_character = CharacterFactory(db_key="Bob", location=self.room)
        target_sheet = CharacterSheetFactory(character=target_character)
        target_persona = target_sheet.primary_persona

        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "content": "waves.",
                "target_names": ["Bob"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        pose_id = response.data["id"]
        assert InteractionTargetPersona.objects.filter(
            interaction_id=pose_id, persona=target_persona
        ).exists()
        assert response.data["target_persona_ids"] == [target_persona.pk]

    @patch("world.scenes.interaction_views.flag_blocked_contact_attempt")
    def test_submit_pose_with_target_names_flags_blocked_contact(self, mock_flag) -> None:
        """Directed REST poses run the same blocked-contact flag as WS/telnet (#2156)."""
        target_character = CharacterFactory(db_key="Carol", location=self.room)
        target_sheet = CharacterSheetFactory(character=target_character)
        target_persona = target_sheet.primary_persona

        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "content": "confronts.",
                "target_names": ["Carol"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_flag.assert_called_once_with(
            initiator_persona=self.persona,
            target_persona=target_persona,
            scene=None,
        )

    def test_submit_pose_with_unresolvable_target_name_is_not_an_error(self) -> None:
        """An unresolvable target_names entry is silently skipped, not rejected (#2156)."""
        response = self.client.post(
            self.url,
            {
                "persona_id": self.persona.pk,
                "content": "waves at nobody.",
                "target_names": ["Nobody"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["target_persona_ids"] == []


class ActionLinksSerializerTests(APITestCase):
    """action_links field is populated by the list endpoint for POSE interactions."""

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

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.client.force_authenticate(user=self.account)

    def test_list_includes_action_links_for_pose_with_linked_actions(self) -> None:
        """GET /api/interactions/ returns action_links populated for a POSE with linked actions."""
        scene = SceneFactory()
        action = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.ACTION,
        )
        pose = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.POSE,
        )
        InteractionAction.objects.create(
            pose=pose,
            action_interaction=action,
            ordering=0,
        )

        url = reverse("interaction-list")
        response = self.client.get(url, {"scene": scene.pk})
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        pose_row = next((r for r in results if r["id"] == pose.pk), None)
        assert pose_row is not None, "POSE interaction not found in results"
        assert "action_links" in pose_row
        assert len(pose_row["action_links"]) == 1
        link = pose_row["action_links"][0]
        assert link["ordering"] == 0
        assert link["action_interaction"]["id"] == action.pk
        assert link["action_interaction"]["mode"] == "action"

    def test_list_includes_empty_action_links_for_pose_without_actions(self) -> None:
        """GET /api/interactions/ returns action_links=[] for a POSE with no linked actions."""
        pose = InteractionFactory(
            persona=self.persona,
            mode=InteractionMode.POSE,
        )

        url = reverse("interaction-list")
        response = self.client.get(url, {"persona": self.persona.pk})
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        pose_row = next((r for r in results if r["id"] == pose.pk), None)
        assert pose_row is not None
        assert pose_row["action_links"] == []


class WithoutPoseLinkFilterTests(APITestCase):
    """Tests for the without_pose_link filter on InteractionFilter."""

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

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.client.force_authenticate(user=self.account)

    def test_without_pose_link_true_excludes_linked_actions(self) -> None:
        """?without_pose_link=true excludes ACTION interactions that have a pose link."""
        scene = SceneFactory()
        unlinked_action = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.ACTION,
        )
        linked_action = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.ACTION,
        )
        pose = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.POSE,
        )
        InteractionAction.objects.create(
            pose=pose,
            action_interaction=linked_action,
            ordering=0,
        )

        url = reverse("interaction-list")
        response = self.client.get(
            url,
            {
                "scene": scene.pk,
                "mode": InteractionMode.ACTION,
                "without_pose_link": "true",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        result_ids = {r["id"] for r in response.data["results"]}
        assert unlinked_action.pk in result_ids
        assert linked_action.pk not in result_ids

    def test_without_pose_link_false_returns_all_actions(self) -> None:
        """?without_pose_link=false returns both linked and unlinked ACTION interactions."""
        scene = SceneFactory()
        unlinked_action = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.ACTION,
        )
        linked_action = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.ACTION,
        )
        pose = InteractionFactory(
            persona=self.persona,
            scene=scene,
            mode=InteractionMode.POSE,
        )
        InteractionAction.objects.create(
            pose=pose,
            action_interaction=linked_action,
            ordering=0,
        )

        url = reverse("interaction-list")
        response = self.client.get(
            url,
            {
                "scene": scene.pk,
                "mode": InteractionMode.ACTION,
                "without_pose_link": "false",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        result_ids = {r["id"] for r in response.data["results"]}
        assert unlinked_action.pk in result_ids
        assert linked_action.pk in result_ids


class InteractionListQueryBudgetTests(APITestCase):
    """Task 5 — pin the query budget for GET /api/interactions/?scene=<id>.

    A fixed N-query budget ensures the endorsement prefetches don't introduce
    N+1 queries as endorsements scale. If the budget creeps, either a prefetch
    path is broken or a new one is needed.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        # Build the requesting user's full identity chain.
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.sheet.primary_persona

        # Build two additional "NPC" sheets as authors of poses.
        cls.alice_sheet = CharacterSheetFactory()
        cls.alice_persona = cls.alice_sheet.primary_persona
        cls.bob_sheet = CharacterSheetFactory()
        cls.bob_persona = cls.bob_sheet.primary_persona

        # Scene with a mix of ENTRY and STANDARD poses.
        cls.scene = SceneFactory()
        cls.resonance = ResonanceFactory()

        # ENTRY pose by Alice.
        cls.entry_pose = InteractionFactory(
            persona=cls.alice_persona,
            pose_kind=PoseKind.ENTRY,
            scene=cls.scene,
        )
        # STANDARD pose by Bob.
        cls.standard_pose = InteractionFactory(
            persona=cls.bob_persona,
            pose_kind=PoseKind.STANDARD,
            scene=cls.scene,
        )
        # Another ENTRY pose by Bob.
        cls.bob_entry_pose = InteractionFactory(
            persona=cls.bob_persona,
            pose_kind=PoseKind.ENTRY,
            scene=cls.scene,
        )

        # Several PoseEndorsements across multiple endorsers.
        cls.endorsement_a = PoseEndorsementFactory(
            endorser_sheet=cls.bob_sheet,
            endorsee_sheet=cls.alice_sheet,
            interaction=cls.entry_pose,
            resonance=cls.resonance,
        )
        cls.endorsement_b = PoseEndorsementFactory(
            endorser_sheet=cls.sheet,
            endorsee_sheet=cls.alice_sheet,
            interaction=cls.entry_pose,
            resonance=cls.resonance,
        )
        # SceneEntryEndorsements for the ENTRY poses.
        cls.scene_entry_a = SceneEntryEndorsementFactory(
            endorser_sheet=cls.bob_sheet,
            endorsee_sheet=cls.alice_sheet,
            scene=cls.scene,
            resonance=cls.resonance,
        )
        cls.scene_entry_b = SceneEntryEndorsementFactory(
            endorser_sheet=cls.sheet,
            endorsee_sheet=cls.bob_sheet,
            scene=cls.scene,
            resonance=cls.resonance,
        )

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.client.force_authenticate(user=self.account)

    def test_interaction_list_query_budget_is_constant(self) -> None:
        """GET ?scene=<id> must not produce N+1 queries as endorsement count grows.

        Query budget pinned after initial observation. If this test fails with a
        higher count, check whether a new prefetch path is needed.
        """
        url = reverse("interaction-list")
        # Run once to observe the count, then assert.
        with self.assertNumQueries(53):  # 49 + #1278 block/mute-gate loads + #2183 (below)
            # #2183 adds exactly 2 flat (not per-row) queries: the
            # dramatic_moment_suggestions Prefetch itself, and the one
            # SceneParticipation.exists() query that resolves viewer_can_gm for
            # the ?scene= filter (see InteractionViewSet.get_serializer_context).
            # Both are bounded by "one query per request", never by row count.
            response = self.client.get(url, {"scene": self.scene.pk})
        assert response.status_code == 200
        assert len(response.data["results"]) == 3

    def test_interaction_list_query_budget_does_not_scale_with_endorser_count(self) -> None:
        """Query count must stay constant as endorser count grows (endorsement prefetches
        must not degenerate into N+1 queries per endorser).

        Uses the same interaction count as the small dataset (3 interactions) but with
        5+ endorsers per pose instead of 2, then asserts the same 49-query budget.
        If this fails with a higher count, an endorser-prefetch path is broken.
        """
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        # Five extra endorser sheets (more than the 2 in the small dataset).
        extra_sheets = [CharacterSheetFactory() for _ in range(5)]
        extra_personas = [s.primary_persona for s in extra_sheets]

        dense_scene = SceneFactory()
        dense_resonance = ResonanceFactory()

        # Same interaction structure as the small dataset: 1 ENTRY + 1 STANDARD + 1 ENTRY.
        dense_entry_a = InteractionFactory(
            persona=extra_personas[0],
            pose_kind=PoseKind.ENTRY,
            scene=dense_scene,
        )
        dense_standard = InteractionFactory(
            persona=extra_personas[1],
            pose_kind=PoseKind.STANDARD,
            scene=dense_scene,
        )
        dense_entry_b = InteractionFactory(
            persona=extra_personas[2],
            pose_kind=PoseKind.ENTRY,
            scene=dense_scene,
        )

        # 5 PoseEndorsements on each ENTRY pose (vs. 2 in the small dataset).
        for endorser_sheet in extra_sheets[1:]:
            PoseEndorsementFactory(
                endorser_sheet=endorser_sheet,
                endorsee_sheet=extra_sheets[0],
                interaction=dense_entry_a,
                resonance=dense_resonance,
            )
            PoseEndorsementFactory(
                endorser_sheet=endorser_sheet,
                endorsee_sheet=extra_sheets[2],
                interaction=dense_entry_b,
                resonance=dense_resonance,
            )
        # Also endorse the STANDARD pose.
        for endorser_sheet in extra_sheets[1:]:
            PoseEndorsementFactory(
                endorser_sheet=endorser_sheet,
                endorsee_sheet=extra_sheets[1],
                interaction=dense_standard,
                resonance=dense_resonance,
            )

        # 5+ SceneEntryEndorsements (vs. 2 in the small dataset).
        for endorser_sheet in extra_sheets[1:]:
            SceneEntryEndorsementFactory(
                endorser_sheet=endorser_sheet,
                endorsee_sheet=extra_sheets[0],
                scene=dense_scene,
                resonance=dense_resonance,
            )
            SceneEntryEndorsementFactory(
                endorser_sheet=endorser_sheet,
                endorsee_sheet=extra_sheets[2],
                scene=dense_scene,
                resonance=dense_resonance,
            )

        url = reverse("interaction-list")
        with self.assertNumQueries(53):  # 49 + #1278 block/mute-gate loads + #2183 (below)
            # #2183 adds exactly 2 flat (not per-row) queries: the
            # dramatic_moment_suggestions Prefetch itself, and the one
            # SceneParticipation.exists() query that resolves viewer_can_gm for
            # the ?scene= filter (see InteractionViewSet.get_serializer_context).
            # Both are bounded by "one query per request", never by row count.
            response = self.client.get(url, {"scene": dense_scene.pk})
        assert response.status_code == 200
        assert len(response.data["results"]) == 3  # same count as small dataset
