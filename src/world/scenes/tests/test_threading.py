"""Tests for conversation threading: serializer fields, push payload, and tabletalk."""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    InteractionTargetPersonaFactory,
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
)
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_services import push_interaction
from world.scenes.place_models import InteractionReceiver


class TestSerializerNewFields(TestCase):
    """InteractionListSerializer includes receiver_persona_ids, place_name, target_persona_ids."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_persona = PersonaFactory()
        cls.receiver_persona = PersonaFactory()
        cls.target_persona = PersonaFactory()
        cls.place = PlaceFactory(name="The Bar")

        cls.interaction = InteractionFactory(
            persona=cls.writer_persona,
            place=cls.place,
        )
        InteractionReceiverFactory(
            interaction=cls.interaction,
            persona=cls.receiver_persona,
        )
        InteractionTargetPersonaFactory(
            interaction=cls.interaction,
            persona=cls.target_persona,
        )

        # Set up cached attributes as the viewset Prefetch would
        cls.interaction.cached_receivers = list(
            InteractionReceiver.objects.filter(interaction=cls.interaction)
        )
        cls.interaction.cached_target_personas = list(cls.interaction.target_personas.all())
        cls.interaction.cached_favorites = []
        cls.interaction.cached_reactions = []

    def test_receiver_persona_ids(self) -> None:
        data = InteractionListSerializer(self.interaction).data
        assert self.receiver_persona.pk in data["receiver_persona_ids"]

    def test_place_name(self) -> None:
        data = InteractionListSerializer(self.interaction).data
        assert data["place_name"] == "The Bar"

    def test_target_persona_ids(self) -> None:
        data = InteractionListSerializer(self.interaction).data
        assert self.target_persona.pk in data["target_persona_ids"]

    def test_no_place_returns_none(self) -> None:
        interaction = InteractionFactory(persona=self.writer_persona)
        interaction.cached_receivers = []
        interaction.cached_target_personas = []
        interaction.cached_favorites = []
        interaction.cached_reactions = []
        data = InteractionListSerializer(interaction).data
        assert data["place_name"] is None
        assert data["receiver_persona_ids"] == []
        assert data["target_persona_ids"] == []


class TestPushPayloadNewFields(TestCase):
    """push_interaction payload includes place, receiver, and target IDs."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.char_a = CharacterFactory(db_key="Alice", location=self.room)
        self.identity_a = CharacterIdentityFactory(character=self.char_a)

    def test_payload_includes_new_fields(self) -> None:
        place = PlaceFactory(name="Corner Booth", room=self.room)
        target_persona = PersonaFactory()
        interaction = InteractionFactory(
            persona=self.identity_a.active_persona,
            content="waves.",
            mode=InteractionMode.POSE,
            place=place,
        )
        InteractionReceiverFactory(
            interaction=interaction,
            persona=target_persona,
        )
        InteractionTargetPersonaFactory(
            interaction=interaction,
            persona=target_persona,
        )

        captured = Mock()
        self.char_a.msg = captured

        push_interaction(interaction)

        assert captured.call_count >= 1
        payload = captured.call_args.kwargs["interaction"][1]
        assert payload["place_id"] == place.pk
        assert payload["place_name"] == "Corner Booth"
        assert target_persona.pk in payload["receiver_persona_ids"]
        assert target_persona.pk in payload["target_persona_ids"]

    def test_payload_defaults_for_public_pose(self) -> None:
        interaction = InteractionFactory(
            persona=self.identity_a.active_persona,
            content="waves.",
            mode=InteractionMode.POSE,
        )

        captured = Mock()
        self.char_a.msg = captured

        push_interaction(interaction)

        payload = captured.call_args.kwargs["interaction"][1]
        assert payload["place_id"] is None
        assert payload["place_name"] is None
        assert payload["receiver_persona_ids"] == []
        assert payload["target_persona_ids"] == []


class TestPoseActionWithTargets(TestCase):
    """PoseAction records target_personas when targets kwarg is provided."""

    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_pose_with_targets_creates_target_rows(self) -> None:
        from actions.definitions.communication import PoseAction
        from world.scenes.models import InteractionTargetPersona

        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        CharacterIdentityFactory(character=char_a)
        identity_b = CharacterIdentityFactory(character=char_b)

        action = PoseAction()
        result = action.run(actor=char_a, text="waves at Bob.", targets=[char_b])
        assert result.success

        # Check that target persona was recorded
        target_entries = InteractionTargetPersona.objects.filter(
            persona=identity_b.active_persona,
        )
        assert target_entries.exists()

    def test_pose_with_place_creates_place_interaction(self) -> None:
        from actions.definitions.communication import PoseAction
        from world.scenes.models import Interaction

        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char_a)
        place = PlaceFactory(name="The Bar", room=room)

        action = PoseAction()
        result = action.run(actor=char_a, text="sits at the bar.", place=place)
        assert result.success

        interaction = Interaction.objects.order_by("-pk").first()
        assert interaction is not None
        assert interaction.place_id == place.pk


class TestTabletalkCommand(TestCase):
    """Tests for CmdTabletalk (tt) command."""

    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_tt_with_place_creates_interaction(self) -> None:
        from commands.evennia_overrides.communication import CmdTabletalk
        from world.scenes.models import Interaction

        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char = CharacterFactory(db_key="Alice", location=room)
        identity = CharacterIdentityFactory(character=char)
        place = PlaceFactory(name="Corner Booth", room=room)
        PlacePresenceFactory(place=place, persona=identity.active_persona)

        cmd = CmdTabletalk()
        cmd.caller = char
        cmd.args = " speaks quietly."
        cmd.raw_string = "tt speaks quietly."
        cmd.cmdset = None
        cmd.cmdset_providers = {}
        cmd.session = None
        cmd.account = None
        cmd.obj = None
        cmd.func()

        interaction = Interaction.objects.order_by("-pk").first()
        assert interaction is not None
        assert interaction.place_id == place.pk
        assert interaction.content == "speaks quietly."

    def test_tt_without_place_sends_error(self) -> None:
        from commands.evennia_overrides.communication import CmdTabletalk

        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char = CharacterFactory(db_key="Alice", location=room)
        CharacterIdentityFactory(character=char)

        messages: list[object] = []
        char.msg = lambda *args, **kwargs: messages.append((args, kwargs))

        cmd = CmdTabletalk()
        cmd.caller = char
        cmd.args = " speaks quietly."
        cmd.raw_string = "tt speaks quietly."
        cmd.cmdset = None
        cmd.cmdset_providers = {}
        cmd.session = None
        cmd.account = None
        cmd.obj = None
        cmd.func()

        # Should have sent an error message about not being at a place
        assert any("not at a place" in str(m) for m in messages)

    def test_tt_no_text_sends_error(self) -> None:
        from commands.evennia_overrides.communication import CmdTabletalk

        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char = CharacterFactory(db_key="Alice", location=room)

        messages: list[object] = []
        char.msg = lambda *args, **kwargs: messages.append((args, kwargs))

        cmd = CmdTabletalk()
        cmd.caller = char
        cmd.args = ""
        cmd.raw_string = "tt"
        cmd.cmdset = None
        cmd.cmdset_providers = {}
        cmd.session = None
        cmd.account = None
        cmd.obj = None
        cmd.func()

        assert any("Tabletalk what?" in str(m) for m in messages)
