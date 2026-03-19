"""Tests for concrete action implementations."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from actions.definitions.movement import DropAction, GetAction, TraverseExitAction
from actions.definitions.perception import InventoryAction, LookAction
from evennia_extensions.factories import ObjectDBFactory
from world.mechanics.constants import ChallengeType
from world.mechanics.factories import ChallengeTemplateFactory
from world.mechanics.models import ChallengeInstance


class LookActionTests(TestCase):
    def test_look_returns_description(self):
        action = LookAction()
        actor = ObjectDBFactory(db_key="Alice")
        target = ObjectDBFactory(db_key="Sword")
        target.db.desc = "A shiny sword"

        result = action.run(actor, target=target)
        assert result.success is True
        assert result.message is not None
        assert "Sword" in result.message

    def test_look_without_target_fails(self):
        action = LookAction()
        actor = ObjectDBFactory(db_key="Alice")
        result = action.run(actor)
        assert result.success is False


class InventoryActionTests(TestCase):
    def test_empty_inventory(self):
        action = InventoryAction()
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        result = action.run(actor)
        assert result.success is True
        assert "not carrying" in result.message

    def test_inventory_with_items(self):
        action = InventoryAction()
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        ObjectDBFactory(db_key="Sword", location=actor)
        result = action.run(actor)
        assert result.success is True
        assert "Sword" in result.message


class SayActionTests(TestCase):
    def test_say_broadcasts_to_location(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        action = SayAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, text="hello")
        assert result.success is True

    def test_say_without_text_fails(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        action = SayAction()
        result = action.run(actor, text="")
        assert result.success is False


class PoseActionTests(TestCase):
    def test_pose_broadcasts(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        action = PoseAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, text="stretches.")
        assert result.success is True


class WhisperActionTests(TestCase):
    def test_whisper_sends_to_target(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        action = WhisperAction()
        with patch.object(target, "msg") as mock_msg:
            result = action.run(actor, target=target, text="secret")
        assert result.success is True
        mock_msg.assert_called_once()

    def test_whisper_without_text_fails(self):
        action = WhisperAction()
        actor = ObjectDBFactory(db_key="Alice")
        target = ObjectDBFactory(db_key="Bob")
        result = action.run(actor, target=target, text="")
        assert result.success is False


class GetActionTests(TestCase):
    def test_get_moves_item_to_actor(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=room)
        action = GetAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item)
        assert result.success is True
        item.refresh_from_db()
        assert item.location == actor


class DropActionTests(TestCase):
    def test_drop_moves_item_to_room(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=actor)
        action = DropAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item)
        assert result.success is True
        item.refresh_from_db()
        assert item.location == room


class TraverseExitActionTests(TestCase):
    def test_traverse_moves_actor(self):
        room1 = ObjectDBFactory(
            db_key="Room1",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        room2 = ObjectDBFactory(
            db_key="Room2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        exit_obj = ObjectDBFactory(
            db_key="north",
            db_typeclass_path="typeclasses.exits.Exit",
            location=room1,
            destination=room2,
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room1,
        )
        action = TraverseExitAction()
        with patch.object(actor, "msg"):
            result = action.run(actor, target=exit_obj)
        assert result.success is True
        actor.refresh_from_db()
        assert actor.location == room2


class TraverseExitWithChallengesTest(TestCase):
    """Test that INHIBITOR challenges block exit traversal."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="ChallengeRoom1",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.dest = ObjectDBFactory(
            db_key="ChallengeRoom2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.exit_obj = ObjectDBFactory(
            db_key="ChallengeExit",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
            destination=self.dest,
        )
        self.actor = ObjectDBFactory(
            db_key="ChallengeTraverser",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )

    def test_inhibitor_challenge_blocks_exit(self) -> None:
        """Active INHIBITOR challenge on exit prevents traversal."""
        template = ChallengeTemplateFactory(
            name="Locked Gate Block",
            challenge_type=ChallengeType.INHIBITOR,
        )
        ChallengeInstance.objects.create(
            template=template,
            location=self.exit_obj,
            is_active=True,
            is_revealed=True,
        )

        action = TraverseExitAction()
        result = action.run(self.actor, target=self.exit_obj)
        assert result.success is False
        assert "blocked" in result.message.lower()
        assert "challenges" in result.data
        assert len(result.data["challenges"]) == 1

    def test_no_challenge_allows_exit(self) -> None:
        """No active challenges means exit is traversable."""
        action = TraverseExitAction()
        with patch.object(self.actor, "msg"):
            result = action.run(self.actor, target=self.exit_obj)
        assert result.success is True
