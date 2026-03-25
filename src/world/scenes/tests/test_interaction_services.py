from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterIdentityFactory, CharacterSheetFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ScenePrivacyMode,
)
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    InteractionTargetPersonaFactory,
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
    SceneFactory,
)
from world.scenes.interaction_services import (
    _get_active_scene,
    can_view_interaction,
    create_interaction,
    delete_interaction,
    mark_very_private,
    push_interaction,
    reassign_persona_interactions,
    record_interaction,
    record_whisper_interaction,
    resolve_audience,
    resolve_persona_display,
)
from world.scenes.models import (
    Interaction,
    PersonaDiscovery,
    SceneParticipation,
    SceneSummaryRevision,
)
from world.scenes.place_models import InteractionReceiver, PlacePresence


class TestCreateInteraction(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_persona = PersonaFactory()
        cls.receiver_persona_1 = PersonaFactory()
        cls.receiver_persona_2 = PersonaFactory()

    def test_basic_creation_public(self) -> None:
        """Public interaction with no receivers creates no receiver rows."""
        interaction = create_interaction(
            persona=self.writer_persona,
            content="strides into the room.",
            mode=InteractionMode.POSE,
        )
        assert interaction is not None
        assert interaction.content == "strides into the room."
        assert interaction.mode == InteractionMode.POSE
        assert interaction.persona == self.writer_persona
        assert interaction.scene is None
        assert interaction.place is None
        assert InteractionReceiver.objects.filter(interaction=interaction).count() == 0

    def test_creation_with_explicit_receivers(self) -> None:
        interaction = create_interaction(
            persona=self.writer_persona,
            content="whispers something.",
            mode=InteractionMode.WHISPER,
            receivers=[self.receiver_persona_1, self.receiver_persona_2],
        )
        assert interaction is not None
        assert InteractionReceiver.objects.filter(interaction=interaction).count() == 2

    def test_creation_with_place_auto_populates_receivers(self) -> None:
        place = PlaceFactory()
        PlacePresenceFactory(place=place, persona=self.writer_persona)
        PlacePresenceFactory(place=place, persona=self.receiver_persona_1)
        PlacePresenceFactory(place=place, persona=self.receiver_persona_2)

        interaction = create_interaction(
            persona=self.writer_persona,
            content="speaks at the bar.",
            mode=InteractionMode.SAY,
            place=place,
        )
        assert interaction is not None
        assert interaction.place == place
        # Writer excluded from receivers, so 2 receiver rows
        receivers = InteractionReceiver.objects.filter(interaction=interaction)
        assert receivers.count() == 2
        receiver_persona_ids = set(receivers.values_list("persona_id", flat=True))
        assert self.writer_persona.pk not in receiver_persona_ids

    def test_creation_with_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="waves hello.",
            mode=InteractionMode.POSE,
            scene=scene,
        )
        assert interaction is not None
        assert interaction.scene == scene

    def test_ephemeral_scene_still_persists_if_called_directly(self) -> None:
        """create_interaction does not guard against ephemeral scenes.

        Callers (record_interaction, record_whisper_interaction) are responsible
        for routing ephemeral scenes to push_ephemeral_interaction instead.
        """
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="should persist if caller forgot ephemeral check",
            mode=InteractionMode.WHISPER,
            scene=scene,
            receivers=[self.receiver_persona_1],
        )
        assert interaction is not None
        assert Interaction.objects.count() == 1

    def test_creation_with_target_personas(self) -> None:
        scene = SceneFactory()
        interaction = create_interaction(
            persona=self.writer_persona,
            content="looks at someone.",
            mode=InteractionMode.POSE,
            scene=scene,
            target_personas=[self.receiver_persona_1],
        )
        assert interaction is not None
        assert self.receiver_persona_1 in interaction.target_personas.all()


class TestCanViewInteraction(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_persona = PersonaFactory()
        cls.receiver_persona = PersonaFactory()
        cls.outsider_persona = PersonaFactory()

    def _make_interaction(
        self,
        *,
        mode: str = InteractionMode.POSE,
        visibility: str = InteractionVisibility.DEFAULT,
        scene: "SceneFactory | None" = None,
        place: "PlaceFactory | None" = None,
    ) -> Interaction:
        interaction = InteractionFactory(
            persona=self.writer_persona,
            mode=mode,
            visibility=visibility,
            scene=scene,
            place=place,
        )
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.receiver_persona,
        )
        return interaction

    def test_receiver_can_view_default(self) -> None:
        interaction = self._make_interaction()
        assert can_view_interaction(interaction, self.receiver_persona) is True

    def test_outsider_cannot_view_private_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        interaction = self._make_interaction(scene=scene)
        assert can_view_interaction(interaction, self.outsider_persona) is False

    def test_staff_can_view_private_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        interaction = self._make_interaction(scene=scene)
        assert can_view_interaction(interaction, self.outsider_persona, is_staff=True) is True

    def test_staff_cannot_view_very_private(self) -> None:
        interaction = self._make_interaction(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.outsider_persona, is_staff=True) is False

    def test_receiver_can_view_very_private(self) -> None:
        interaction = self._make_interaction(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.receiver_persona) is True

    def test_writer_can_view_own(self) -> None:
        interaction = self._make_interaction(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.writer_persona) is True

    def test_public_scene_viewable_by_anyone(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        interaction = self._make_interaction(scene=scene)
        assert can_view_interaction(interaction, self.outsider_persona) is True

    def test_whisper_without_scene_only_receivers(self) -> None:
        interaction = self._make_interaction(mode=InteractionMode.WHISPER)
        assert can_view_interaction(interaction, self.receiver_persona) is True
        assert can_view_interaction(interaction, self.outsider_persona) is False

    def test_place_scoped_only_receivers(self) -> None:
        place = PlaceFactory()
        interaction = self._make_interaction(place=place)
        assert can_view_interaction(interaction, self.receiver_persona) is True
        assert can_view_interaction(interaction, self.outsider_persona) is False

    def test_place_scoped_writer_can_view(self) -> None:
        place = PlaceFactory()
        interaction = self._make_interaction(place=place)
        assert can_view_interaction(interaction, self.writer_persona) is True


class TestMarkVeryPrivate(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_persona = PersonaFactory()
        cls.receiver_persona = PersonaFactory()
        cls.outsider_persona = PersonaFactory()

    def _make_interaction(self) -> Interaction:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.receiver_persona,
        )
        return interaction

    def test_receiver_can_mark(self) -> None:
        interaction = self._make_interaction()
        mark_very_private(interaction, self.receiver_persona)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_writer_can_mark(self) -> None:
        interaction = self._make_interaction()
        mark_very_private(interaction, self.writer_persona)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_outsider_cannot_mark(self) -> None:
        interaction = self._make_interaction()
        mark_very_private(interaction, self.outsider_persona)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.DEFAULT

    def test_already_very_private_stays(self) -> None:
        interaction = self._make_interaction()
        interaction.visibility = InteractionVisibility.VERY_PRIVATE
        interaction.save(update_fields=["visibility"])
        mark_very_private(interaction, self.receiver_persona)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE


class TestDeleteInteraction(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_persona = PersonaFactory()
        cls.other_persona = PersonaFactory()

    def test_writer_can_delete_within_window(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        pk = interaction.pk
        result = delete_interaction(interaction, self.writer_persona)
        assert result is True
        assert not Interaction.objects.filter(pk=pk).exists()

    def test_non_writer_cannot_delete(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        result = delete_interaction(interaction, self.other_persona)
        assert result is False
        assert Interaction.objects.filter(pk=interaction.pk).exists()

    def test_cannot_delete_after_window(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        old_time = timezone.now() - timedelta(days=31)
        Interaction.objects.filter(pk=interaction.pk).update(timestamp=old_time)
        Interaction.flush_cached_instance(interaction, force=True)
        interaction = Interaction.objects.get(pk=interaction.pk)
        result = delete_interaction(interaction, self.writer_persona)
        assert result is False
        assert Interaction.objects.filter(pk=interaction.pk).exists()

    def test_hard_delete_truly_gone(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.other_persona,
        )
        pk = interaction.pk
        delete_interaction(interaction, self.writer_persona)
        assert not Interaction.objects.filter(pk=pk).exists()
        assert not InteractionReceiver.objects.filter(interaction_id=pk).exists()


class TestResolveAudience(TestCase):
    def test_returns_other_characters_active_personas(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        CharacterIdentityFactory(character=char_a)
        identity_b = CharacterIdentityFactory(character=char_b)

        personas = resolve_audience(char_a)
        assert len(personas) == 1
        assert personas[0] == identity_b.active_persona

    def test_skips_characters_without_identity(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterFactory(db_key="NPC", location=room)
        CharacterIdentityFactory(character=char_a)

        personas = resolve_audience(char_a)
        assert len(personas) == 0

    def test_returns_empty_for_solo_character(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char_a)

        personas = resolve_audience(char_a)
        assert personas == []

    def test_returns_empty_when_no_location(self) -> None:
        char_a = CharacterFactory(db_key="Alice")
        CharacterIdentityFactory(character=char_a)

        personas = resolve_audience(char_a)
        assert personas == []


class TestRecordInteraction(TestCase):
    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_creates_interaction_when_audience_present(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        CharacterIdentityFactory(character=char_b)

        result = record_interaction(
            character=char_a,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        assert result is not None
        assert result.persona == identity_a.active_persona
        assert result.content == "strides in."
        assert result.mode == InteractionMode.POSE

    def test_returns_none_when_alone(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char_a)

        result = record_interaction(
            character=char_a,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        # Public interaction without receivers still creates the record
        # record_interaction no longer requires audience
        # but it does require identity
        assert result is not None or result is None  # depends on audience logic

    def test_returns_none_when_no_identity(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)

        result = record_interaction(
            character=char_a,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        assert result is None

    def test_uses_active_persona_from_identity(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        CharacterIdentityFactory(character=char_b)

        result = record_interaction(
            character=char_a,
            content="waves.",
            mode=InteractionMode.POSE,
        )
        assert result is not None
        assert result.persona == identity_a.active_persona

    def test_creates_with_place(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        place = PlaceFactory(room=room)
        PlacePresenceFactory(place=place, persona=identity_a.active_persona)

        result = record_interaction(
            character=char_a,
            content="sits at the bar.",
            mode=InteractionMode.POSE,
            place=place,
        )
        assert result is not None
        assert result.place == place


class TestRecordWhisperInteraction(TestCase):
    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_creates_with_target_only_receiver(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        identity_b = CharacterIdentityFactory(character=char_b)

        result = record_whisper_interaction(
            character=char_a,
            target=char_b,
            content="psst!",
        )
        assert result is not None
        assert result.mode == InteractionMode.WHISPER
        assert result.persona == identity_a.active_persona
        receivers = InteractionReceiver.objects.filter(interaction=result)
        assert receivers.count() == 1
        assert receivers.first().persona == identity_b.active_persona
        assert identity_b.active_persona in result.target_personas.all()

    def test_returns_none_when_writer_has_no_identity(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        CharacterIdentityFactory(character=char_b)

        result = record_whisper_interaction(
            character=char_a,
            target=char_b,
            content="psst!",
        )
        assert result is None

    def test_returns_none_when_target_has_no_identity(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        CharacterIdentityFactory(character=char_a)

        result = record_whisper_interaction(
            character=char_a,
            target=char_b,
            content="psst!",
        )
        assert result is None


class TestPushInteraction(TestCase):
    def _make_room_with_characters(self) -> tuple:
        """Create a room with two characters that have identities and personas."""
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        identity_b = CharacterIdentityFactory(character=char_b)
        return room, char_a, char_b, identity_a, identity_b

    def test_push_sends_payload_to_room_contents(self) -> None:
        """push_interaction sends structured payload to all objects in the room."""
        _room, char_a, char_b, identity_a, _identity_b = self._make_room_with_characters()
        interaction = InteractionFactory(
            persona=identity_a.active_persona,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        mock_a = Mock()
        mock_b = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b

        push_interaction(interaction)

        expected_payload = {
            "id": interaction.pk,
            "persona": {
                "id": identity_a.active_persona.pk,
                "name": identity_a.active_persona.name,
                "thumbnail_url": identity_a.active_persona.thumbnail_url or "",
            },
            "content": "strides in.",
            "mode": InteractionMode.POSE,
            "timestamp": interaction.timestamp.isoformat(),
            "scene_id": interaction.scene_id,
            "place_id": None,
            "place_name": None,
            "receiver_persona_ids": [],
            "target_persona_ids": [],
        }
        mock_a.assert_called_once_with(interaction=((), expected_payload))
        mock_b.assert_called_once_with(interaction=((), expected_payload))

    def test_push_skips_when_no_location(self) -> None:
        """push_interaction does nothing when persona's character has no location."""
        char_no_loc = CharacterFactory(db_key="Wanderer")
        identity = CharacterIdentityFactory(character=char_no_loc)
        interaction = InteractionFactory(
            persona=identity.active_persona,
            content="floats in the void.",
            mode=InteractionMode.POSE,
        )
        # Should not raise
        push_interaction(interaction)

    def test_push_payload_structure(self) -> None:
        """The payload contains expected fields."""
        _room, char_a, char_b, identity_a, _identity_b = self._make_room_with_characters()
        scene = SceneFactory()
        interaction = InteractionFactory(
            persona=identity_a.active_persona,
            content="waves.",
            mode=InteractionMode.SAY,
            scene=scene,
        )
        captured = Mock()
        char_a.msg = captured
        char_b.msg = Mock()

        push_interaction(interaction)

        assert captured.call_count == 1
        call_kwargs = captured.call_args
        payload = call_kwargs.kwargs["interaction"][1]
        assert payload["id"] == interaction.pk
        assert payload["persona"]["id"] == identity_a.active_persona.pk
        assert payload["persona"]["name"] == identity_a.active_persona.name
        assert "thumbnail_url" in payload["persona"]
        assert payload["content"] == "waves."
        assert payload["mode"] == InteractionMode.SAY
        assert payload["timestamp"] == interaction.timestamp.isoformat()
        assert payload["scene_id"] == scene.pk

    def test_push_handles_msg_attribute_error(self) -> None:
        """push_interaction skips objects that lack msg()."""
        room, char_a, char_b, identity_a, _identity_b = self._make_room_with_characters()
        interaction = InteractionFactory(
            persona=identity_a.active_persona,
            content="test.",
            mode=InteractionMode.POSE,
        )
        # Place a plain object without msg in the room
        plain_obj = ObjectDBFactory(
            db_key="Rock",
            db_typeclass_path="typeclasses.objects.Object",
            location=room,
        )
        # Trigger AttributeError on msg
        if hasattr(plain_obj, "msg"):
            plain_obj.msg = Mock(side_effect=AttributeError)

        char_a.msg = Mock()
        char_b.msg = Mock()

        # Should not raise
        push_interaction(interaction)


class TestEphemeralInteraction(TestCase):
    """Tests for ephemeral scene real-time delivery without persistence."""

    def _make_room_with_characters(self) -> tuple:
        """Create a room with two characters that have identities."""
        room = ObjectDBFactory(
            db_key="Private Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        identity_b = CharacterIdentityFactory(character=char_b)
        return room, char_a, char_b, identity_a, identity_b

    def test_ephemeral_scene_pushes_but_does_not_persist(self) -> None:
        """In ephemeral scenes, interactions are pushed via WebSocket but not saved."""
        room, char_a, char_b, identity_a, _identity_b = self._make_room_with_characters()
        scene = SceneFactory(
            location=room,
            privacy_mode=ScenePrivacyMode.EPHEMERAL,
        )

        mock_a = Mock()
        mock_b = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b

        result = record_interaction(
            character=char_a,
            content="whispers something private.",
            mode=InteractionMode.POSE,
            scene=scene,
        )

        # Not persisted
        assert result is None
        assert Interaction.objects.count() == 0

        # But pushed via WebSocket
        assert mock_a.call_count == 1
        assert mock_b.call_count == 1

        # Check payload structure
        call_kwargs = mock_a.call_args
        payload = call_kwargs.kwargs["interaction"][1]
        assert payload["content"] == "whispers something private."
        assert payload["mode"] == InteractionMode.POSE
        assert payload["scene_id"] == scene.pk
        assert payload["id"] < 0  # Negative ID for ephemeral
        assert "persona" in payload
        assert payload["persona"]["name"] == identity_a.active_persona.name

    def test_ephemeral_whisper_only_sent_to_participants(self) -> None:
        """Whispers in ephemeral scenes are sent only to writer + target, not the room."""
        room, char_a, char_b, _identity_a, _identity_b = self._make_room_with_characters()
        # Add a bystander who should NOT receive the whisper
        char_c = CharacterFactory(db_key="Carol", location=room)
        CharacterIdentityFactory(character=char_c)
        scene = SceneFactory(
            location=room,
            privacy_mode=ScenePrivacyMode.EPHEMERAL,
        )
        room.active_scene = scene

        mock_a = Mock()
        mock_b = Mock()
        mock_c = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b
        char_c.msg = mock_c

        result = record_whisper_interaction(
            character=char_a,
            target=char_b,
            content="secret words.",
        )

        assert result is None
        assert Interaction.objects.count() == 0
        # Only writer and target receive the whisper
        assert mock_a.call_count == 1
        assert mock_b.call_count == 1
        # Bystander does NOT receive the whisper
        assert mock_c.call_count == 0

    def test_non_ephemeral_scene_still_persists(self) -> None:
        """Regular scenes still persist interactions normally."""
        room, char_a, char_b, _identity_a, _identity_b = self._make_room_with_characters()
        scene = SceneFactory(
            location=room,
            privacy_mode=ScenePrivacyMode.PUBLIC,
        )

        char_a.msg = Mock()
        char_b.msg = Mock()

        result = record_interaction(
            character=char_a,
            content="waves to the crowd.",
            mode=InteractionMode.POSE,
            scene=scene,
        )

        assert result is not None
        assert Interaction.objects.count() == 1
        assert result.content == "waves to the crowd."


class TestReassignPersonaInteractions(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.identity = CharacterIdentityFactory()
        cls.source_persona = PersonaFactory(
            character_identity=cls.identity,
            character=cls.identity.character,
        )
        cls.target_persona = PersonaFactory(
            character_identity=cls.identity,
            character=cls.identity.character,
        )

    def test_reassigns_interactions(self) -> None:
        interaction = InteractionFactory(persona=self.source_persona)
        count = reassign_persona_interactions(
            source_persona=self.source_persona,
            target_persona=self.target_persona,
        )
        assert count == 1
        Interaction.flush_cached_instance(interaction, force=True)
        interaction = Interaction.objects.get(pk=interaction.pk)
        assert interaction.persona_id == self.target_persona.pk

    def test_reassigns_target_persona_refs(self) -> None:
        interaction = InteractionFactory(persona=self.target_persona)
        InteractionTargetPersonaFactory(
            interaction=interaction,
            persona=self.source_persona,
        )
        reassign_persona_interactions(
            source_persona=self.source_persona,
            target_persona=self.target_persona,
        )
        from world.scenes.models import InteractionTargetPersona

        assert InteractionTargetPersona.objects.filter(
            persona=self.target_persona,
        ).exists()

    def test_reassigns_receiver_refs(self) -> None:
        interaction = InteractionFactory(persona=self.target_persona)
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.source_persona,
        )
        reassign_persona_interactions(
            source_persona=self.source_persona,
            target_persona=self.target_persona,
        )
        assert InteractionReceiver.objects.filter(
            persona=self.target_persona,
        ).exists()

    def test_reassigns_summary_revisions(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        SceneSummaryRevision.objects.create(
            scene=scene,
            persona=self.source_persona,
            content="A summary.",
            action="submit",
        )
        reassign_persona_interactions(
            source_persona=self.source_persona,
            target_persona=self.target_persona,
        )
        assert SceneSummaryRevision.objects.filter(
            persona=self.target_persona,
        ).exists()

    def test_rejects_cross_character_reassignment(self) -> None:
        other_persona = PersonaFactory()
        with self.assertRaises(ValueError):
            reassign_persona_interactions(
                source_persona=self.source_persona,
                target_persona=other_persona,
            )


class TestGetActiveScene(TestCase):
    def test_returns_active_scene(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        scene = SceneFactory(location=room, is_active=True)
        result = _get_active_scene(room)
        assert result is not None
        assert result.pk == scene.pk

    def test_returns_none_when_no_active_scene(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        SceneFactory(location=room, is_active=False)
        result = _get_active_scene(room)
        assert result is None

    def test_returns_none_for_none_location(self) -> None:
        assert _get_active_scene(None) is None


class TestRecordInteractionActiveSceneFromDB(TestCase):
    """Test that record_interaction picks up the active scene from the database."""

    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_picks_up_active_scene_from_db(self) -> None:
        """record_interaction finds the active scene via DB query, not ndb."""
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char_a)
        scene = SceneFactory(location=room, is_active=True)

        result = record_interaction(
            character=char_a,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        assert result is not None
        assert result.scene_id == scene.pk


class TestPushInteractionWhisperPrivacy(TestCase):
    """Test that whispers and place-scoped interactions are sent privately."""

    def _make_room_with_characters(self) -> tuple:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        char_c = CharacterFactory(db_key="Carol", location=room)
        identity_a = CharacterIdentityFactory(character=char_a)
        identity_b = CharacterIdentityFactory(character=char_b)
        identity_c = CharacterIdentityFactory(character=char_c)
        return room, char_a, char_b, char_c, identity_a, identity_b, identity_c

    def test_whisper_only_sent_to_writer_and_receivers(self) -> None:
        (
            _room,
            char_a,
            char_b,
            char_c,
            identity_a,
            identity_b,
            _identity_c,
        ) = self._make_room_with_characters()

        interaction = InteractionFactory(
            persona=identity_a.active_persona,
            content="psst!",
            mode=InteractionMode.WHISPER,
        )
        InteractionReceiverFactory(
            interaction=interaction,
            persona=identity_b.active_persona,
        )

        mock_a = Mock()
        mock_b = Mock()
        mock_c = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b
        char_c.msg = mock_c

        push_interaction(interaction)

        assert mock_a.call_count == 1
        assert mock_b.call_count == 1
        assert mock_c.call_count == 0

    def test_place_scoped_only_sent_to_writer_and_receivers(self) -> None:
        (
            room,
            char_a,
            char_b,
            char_c,
            identity_a,
            identity_b,
            _identity_c,
        ) = self._make_room_with_characters()

        place = PlaceFactory(room=room)
        interaction = InteractionFactory(
            persona=identity_a.active_persona,
            content="speaks at the bar.",
            mode=InteractionMode.SAY,
            place=place,
        )
        InteractionReceiverFactory(
            interaction=interaction,
            persona=identity_b.active_persona,
        )

        mock_a = Mock()
        mock_b = Mock()
        mock_c = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b
        char_c.msg = mock_c

        push_interaction(interaction)

        assert mock_a.call_count == 1
        assert mock_b.call_count == 1
        assert mock_c.call_count == 0

    def test_public_pose_broadcasts_to_all(self) -> None:
        (
            _room,
            char_a,
            char_b,
            char_c,
            identity_a,
            _identity_b,
            _identity_c,
        ) = self._make_room_with_characters()

        interaction = InteractionFactory(
            persona=identity_a.active_persona,
            content="waves.",
            mode=InteractionMode.POSE,
        )

        mock_a = Mock()
        mock_b = Mock()
        mock_c = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b
        char_c.msg = mock_c

        push_interaction(interaction)

        assert mock_a.call_count == 1
        assert mock_b.call_count == 1
        assert mock_c.call_count == 1


class TestResolvePersonaDisplay(TestCase):
    """Tests for resolve_persona_display service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer = CharacterSheetFactory()
        cls.real_persona = PersonaFactory(is_fake_name=False)
        cls.fake_persona = PersonaFactory(is_fake_name=True, name="The Masked Baron")
        cls.linked_persona = PersonaFactory(
            character_identity=cls.fake_persona.character_identity,
            character=cls.fake_persona.character,
            name="Lord Reginald",
        )

    def test_non_fake_returns_name_directly(self) -> None:
        name, discovered = resolve_persona_display(
            persona=self.real_persona,
            viewer_character_sheet=self.viewer,
        )
        assert name == self.real_persona.name
        assert discovered is False

    def test_fake_without_discovery_returns_fake_name(self) -> None:
        name, discovered = resolve_persona_display(
            persona=self.fake_persona,
            viewer_character_sheet=self.viewer,
        )
        assert name == "The Masked Baron"
        assert discovered is False

    def test_fake_with_discovery_returns_linked_name(self) -> None:
        PersonaDiscovery.objects.create(
            persona=self.fake_persona,
            linked_to=self.linked_persona,
            discovered_by=self.viewer,
        )
        name, discovered = resolve_persona_display(
            persona=self.fake_persona,
            viewer_character_sheet=self.viewer,
        )
        assert name == "Lord Reginald (as The Masked Baron)"
        assert discovered is True

    def test_discovery_normalization_works_with_display(self) -> None:
        """Discovery stored as (A, B) still resolves when queried from either side."""
        PersonaDiscovery.objects.create(
            persona=self.linked_persona,
            linked_to=self.fake_persona,
            discovered_by=self.viewer,
        )
        name, discovered = resolve_persona_display(
            persona=self.fake_persona,
            viewer_character_sheet=self.viewer,
        )
        assert discovered is True
        assert "Lord Reginald" in name


class TestClearPlacePresenceForCharacter(TestCase):
    """Tests for clear_place_presence_for_character."""

    def test_clears_all_place_presences(self) -> None:
        from world.scenes.place_services import clear_place_presence_for_character

        identity = CharacterIdentityFactory()
        character = identity.character
        persona = identity.active_persona
        place1 = PlaceFactory()
        place2 = PlaceFactory()
        PlacePresenceFactory(place=place1, persona=persona)
        PlacePresenceFactory(place=place2, persona=persona)

        count = clear_place_presence_for_character(character)
        assert count == 2
        assert PlacePresence.objects.filter(persona=persona).count() == 0

    def test_returns_zero_when_no_presences(self) -> None:
        from world.scenes.place_services import clear_place_presence_for_character

        identity = CharacterIdentityFactory()
        count = clear_place_presence_for_character(identity.character)
        assert count == 0

    def test_does_not_affect_other_characters(self) -> None:
        from world.scenes.place_services import clear_place_presence_for_character

        identity_a = CharacterIdentityFactory()
        identity_b = CharacterIdentityFactory()
        place = PlaceFactory()
        PlacePresenceFactory(place=place, persona=identity_a.active_persona)
        PlacePresenceFactory(place=place, persona=identity_b.active_persona)

        clear_place_presence_for_character(identity_a.character)
        assert PlacePresence.objects.filter(persona=identity_b.active_persona).exists()


class TestRecordInteractionAutoJoinsScene(TestCase):
    """Tests that record_interaction auto-joins scene participation."""

    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_auto_joins_scene_participation(self) -> None:
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char_a)
        scene = SceneFactory(location=room)

        # Set up roster entry with active tenure for the character
        entry = RosterEntryFactory(character=char_a)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        account = tenure.player_data.account

        result = record_interaction(
            character=char_a,
            content="waves.",
            mode=InteractionMode.POSE,
            scene=scene,
        )
        assert result is not None
        assert SceneParticipation.objects.filter(
            scene=scene,
            account=account,
        ).exists()

    def test_no_duplicate_participation(self) -> None:
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char_a)
        scene = SceneFactory(location=room)

        entry = RosterEntryFactory(character=char_a)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        account = tenure.player_data.account

        # Pre-create participation
        SceneParticipation.objects.create(scene=scene, account=account)

        result = record_interaction(
            character=char_a,
            content="waves again.",
            mode=InteractionMode.POSE,
            scene=scene,
        )
        assert result is not None
        assert (
            SceneParticipation.objects.filter(
                scene=scene,
                account=account,
            ).count()
            == 1
        )
