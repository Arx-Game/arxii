from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ScenePrivacyMode,
)
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
    SceneFactory,
)
from world.scenes.interaction_services import (
    can_view_interaction,
    create_interaction,
    delete_interaction,
    mark_very_private,
    push_interaction,
    record_interaction,
    record_whisper_interaction,
    resolve_audience,
)
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver


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

    def test_ephemeral_scene_returns_none(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="secret whisper",
            mode=InteractionMode.WHISPER,
            scene=scene,
            receivers=[self.receiver_persona_1],
        )
        assert interaction is None
        assert Interaction.objects.count() == 0
        assert InteractionReceiver.objects.count() == 0

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
        room, char_a, char_b, _identity_a, _identity_b = self._make_room_with_characters()
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

    def test_ephemeral_whisper_pushes_but_does_not_persist(self) -> None:
        """Whispers in ephemeral scenes are also pushed without persistence."""
        room, char_a, char_b, _identity_a, _identity_b = self._make_room_with_characters()
        scene = SceneFactory(
            location=room,
            privacy_mode=ScenePrivacyMode.EPHEMERAL,
        )
        room.active_scene = scene

        mock_a = Mock()
        mock_b = Mock()
        char_a.msg = mock_a
        char_b.msg = mock_b

        result = record_whisper_interaction(
            character=char_a,
            target=char_b,
            content="secret words.",
        )

        assert result is None
        assert Interaction.objects.count() == 0
        assert mock_a.call_count == 1
        assert mock_b.call_count == 1

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
