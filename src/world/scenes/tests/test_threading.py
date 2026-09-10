"""Tests for conversation threading: serializer fields, push payload, and tabletalk."""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    InteractionTargetPersonaFactory,
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
    SceneFactory,
)
from world.scenes.interaction_serializers import (
    InteractionListSerializer,
    ReplyTargetSerializer,
)
from world.scenes.interaction_services import create_interaction, push_interaction
from world.scenes.models import Interaction, InteractionThread
from world.scenes.place_models import InteractionReceiver
from world.scenes.thread_services import (
    InteractionThreadError,
    ReplyTarget,
    assign_interaction_thread,
)


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

    def test_thread_id_is_serialized(self) -> None:
        thread = InteractionThread.objects.create(
            holder_kind=InteractionThread.HolderKind.SCENE,
            holder_id=11,
            scene_id=11,
        )
        self.interaction.thread = thread
        self.interaction.save(update_fields=["thread"])

        data = InteractionListSerializer(self.interaction).data

        assert data["thread_id"] == str(thread.pk)
        assert data["reply_to"] is None

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
        self.identity_a = CharacterSheetFactory(character=self.char_a)

    def test_payload_includes_new_fields(self) -> None:
        place = PlaceFactory(name="Corner Booth", room=RoomProfileFactory(objectdb=self.room))
        target_persona = PersonaFactory()
        interaction = InteractionFactory(
            persona=self.identity_a.primary_persona,
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
            persona=self.identity_a.primary_persona,
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
        CharacterSheetFactory(character=char_a)
        identity_b = CharacterSheetFactory(character=char_b)

        action = PoseAction()
        result = action.run(actor=char_a, text="waves at Bob.", targets=[char_b])
        assert result.success

        # Check that target persona was recorded
        target_entries = InteractionTargetPersona.objects.filter(
            persona=identity_b.primary_persona,
        )
        assert target_entries.exists()

    def test_pose_with_place_creates_place_interaction(self) -> None:
        from actions.definitions.communication import PoseAction

        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterSheetFactory(character=char_a)
        place = PlaceFactory(name="The Bar", room=RoomProfileFactory(objectdb=room))

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
        identity = CharacterSheetFactory(character=char)
        place = PlaceFactory(name="Corner Booth", room=RoomProfileFactory(objectdb=room))
        PlacePresenceFactory(place=place, persona=identity.primary_persona)

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
        CharacterSheetFactory(character=char)

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


class TestInteractionThreadModel(TestCase):
    """Interaction threads are nullable flat membership containers."""

    def test_interaction_thread_membership_and_set_null(self) -> None:
        interaction = InteractionFactory()
        thread = InteractionThread.objects.create(
            holder_kind=InteractionThread.HolderKind.SCENE,
            holder_id=7,
            scene_id=7,
        )
        interaction.thread = thread
        interaction.save(update_fields=["thread"])

        interaction.refresh_from_db()
        assert interaction.thread_id == thread.pk

        thread.delete()
        thread_id = (
            Interaction.objects.filter(pk=interaction.pk).values_list("thread_id", flat=True).get()
        )
        assert thread_id is None

    def test_thread_parent_is_optional(self) -> None:
        thread = InteractionThread.objects.create(
            holder_kind=InteractionThread.HolderKind.WHISPER,
            party_key="3,7",
        )

        assert thread.parent_id is None
        assert thread.pk is not None


class TestInteractionThreadAssignment(TestCase):
    """Reply targets create and reuse flat threads without parent links."""

    def test_scene_target_creates_and_reuses_thread(self) -> None:
        account = AccountFactory()
        scene = SceneFactory()
        target = InteractionFactory(scene=scene, writer_account=account)
        first_reply = InteractionFactory(scene=scene, writer_account=account)

        assignment = assign_interaction_thread(
            interaction=first_reply,
            reply_target=ReplyTarget(target.pk, target.timestamp),
            account_id=account.pk,
        )
        thread = assignment.thread

        assert target.thread_id == thread.pk
        assert first_reply.thread_id == thread.pk
        assert thread.parent_id is None

        second_reply = InteractionFactory(scene=scene, writer_account=account)
        reused = assign_interaction_thread(
            interaction=second_reply,
            reply_target=ReplyTarget(target.pk, target.timestamp),
            account_id=account.pk,
        )

        assert reused.thread.pk == thread.pk
        assert second_reply.thread_id == thread.pk

    def test_mismatched_scene_is_unavailable(self) -> None:
        account = AccountFactory()
        target = InteractionFactory(scene=SceneFactory(), writer_account=account)
        reply = InteractionFactory(scene=SceneFactory(), writer_account=account)

        with self.assertRaises(InteractionThreadError):
            assign_interaction_thread(
                interaction=reply,
                reply_target=ReplyTarget(target.pk, target.timestamp),
                account_id=account.pk,
            )

    def test_inaccessible_target_is_unavailable(self) -> None:
        writer = AccountFactory()
        viewer = AccountFactory()
        private_scene = SceneFactory(
            privacy_mode=ScenePrivacyMode.PRIVATE,
            participants=[writer],
        )
        target = InteractionFactory(scene=private_scene, writer_account=writer)
        reply = InteractionFactory(scene=private_scene, writer_account=viewer)

        with self.assertRaises(InteractionThreadError):
            assign_interaction_thread(
                interaction=reply,
                reply_target=ReplyTarget(target.pk, target.timestamp),
                account_id=viewer.pk,
            )

    def test_scene_less_target_is_unavailable(self) -> None:
        account = AccountFactory()
        target = InteractionFactory(writer_account=account)
        reply = InteractionFactory(writer_account=account)

        with self.assertRaises(InteractionThreadError) as error:
            assign_interaction_thread(
                interaction=reply,
                reply_target=ReplyTarget(target.pk, target.timestamp),
                account_id=account.pk,
            )

        assert error.exception.code == "reply_target_unavailable"

    def test_create_interaction_assigns_thread_atomically(self) -> None:
        account = AccountFactory()
        scene = SceneFactory()
        persona = PersonaFactory()

        with patch(
            "world.scenes.interaction_services._get_account_for_persona",
            return_value=account.pk,
        ):
            target = create_interaction(
                persona=persona,
                content="root",
                mode=InteractionMode.POSE,
                scene=scene,
            )
            reply = create_interaction(
                persona=persona,
                content="reply",
                mode=InteractionMode.POSE,
                scene=scene,
                reply_to=ReplyTarget(target.pk, target.timestamp),
            )

        assert reply.thread_id is not None
        assert (
            Interaction.objects.filter(pk=target.pk).values_list("thread_id", flat=True).get()
            == reply.thread_id
        )


class TestReplyTargetSerializer(TestCase):
    """Reply targets are write-only serializer references."""

    def test_accepts_timezone_aware_reference(self) -> None:
        serializer = ReplyTargetSerializer(data={"id": 4, "timestamp": "2026-09-10T12:00:00Z"})

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["id"] == 4

    def test_rejects_unknown_fields(self) -> None:
        serializer = ReplyTargetSerializer(
            data={"id": 4, "timestamp": "2026-09-10T12:00:00Z", "thread_id": "x"}
        )

        assert not serializer.is_valid()

    def test_rejects_naive_timestamp(self) -> None:
        serializer = ReplyTargetSerializer(data={"id": 4, "timestamp": "2026-09-10T12:00:00"})

        assert not serializer.is_valid()
