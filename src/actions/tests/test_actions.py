"""Tests for concrete action implementations."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from actions.definitions.movement import DropAction, GetAction, TraverseExitAction
from actions.definitions.perception import InventoryAction, LookAction
from evennia_extensions.factories import ObjectDBFactory
from world.conditions.factories import CapabilityTypeFactory
from world.obstacles.constants import DiscoveryType
from world.obstacles.factories import (
    BypassCapabilityRequirementFactory,
    BypassOptionFactory,
    ObstacleInstanceFactory,
    ObstaclePropertyFactory,
    ObstacleTemplateFactory,
)


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


class TraverseExitWithObstaclesTest(TestCase):
    """Tests for TraverseExitAction obstacle integration."""

    def test_clear_exit_traverses_normally(self) -> None:
        """Exit with no obstacles works as before."""
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        dest = ObjectDBFactory(
            db_key="Destination",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        exit_obj = ObjectDBFactory(
            db_key="North",
            db_typeclass_path="typeclasses.exits.Exit",
            location=room,
            destination=dest,
        )
        action = TraverseExitAction()
        with patch.object(actor, "msg"):
            result = action.run(actor, target=exit_obj)
        assert result.success is True

    def test_blocked_exit_returns_obstacle_info(self) -> None:
        """Exit with active obstacle blocks traversal and returns details."""
        room = ObjectDBFactory(
            db_key="Room2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        dest = ObjectDBFactory(
            db_key="Destination2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        exit_obj = ObjectDBFactory(
            db_key="South",
            db_typeclass_path="typeclasses.exits.Exit",
            location=room,
            destination=dest,
        )

        tall = ObstaclePropertyFactory(name="tall_action")
        fly_bypass = BypassOptionFactory(
            obstacle_property=tall,
            name="Fly Over",
            discovery_type=DiscoveryType.OBVIOUS,
        )
        flight = CapabilityTypeFactory(name="flight_action")
        BypassCapabilityRequirementFactory(
            bypass_option=fly_bypass,
            capability_type=flight,
            minimum_value=1,
        )
        template = ObstacleTemplateFactory(name="High Ledge Action")
        template.properties.set([tall])
        ObstacleInstanceFactory(template=template, target=exit_obj)

        action = TraverseExitAction()
        result = action.run(actor, target=exit_obj)
        assert result.success is False
        assert "obstacles" in result.data
        assert len(result.data["obstacles"]) == 1
        assert result.data["obstacles"][0]["name"] == "High Ledge Action"
        assert len(result.data["obstacles"][0]["bypass_options"]) == 1
