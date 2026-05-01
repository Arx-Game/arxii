"""Tests for concrete action implementations."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from actions.definitions.movement import DropAction, GetAction, GiveAction, TraverseExitAction
from actions.definitions.perception import InventoryAction, LookAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.items.constants import BodyRegion, EquipmentLayer, OwnershipEventType
from world.items.factories import ItemInstanceFactory
from world.items.models import EquippedItem, OwnershipEvent
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
        account = AccountFactory(username="get_action_account")
        actor = CharacterFactory(db_key="Alice", location=room)
        actor.db_account = account
        actor.save()

        item_obj = ObjectDBFactory(db_key="Sword", location=room)
        item_instance = ItemInstanceFactory(game_object=item_obj)

        action = GetAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        item_obj.refresh_from_db()
        assert item_obj.location == actor

        # Pick-up sets owner when previously unowned.
        item_instance.refresh_from_db()
        assert item_instance.owner == account

    def test_get_without_item_instance_fails_gracefully(self):
        room = ObjectDBFactory(
            db_key="GetRoomNoInstance",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="GetActorNoInstance", location=room)
        # Plain ObjectDB with no ItemInstance row.
        bare_object = ObjectDBFactory(db_key="GetBareObject", location=room)

        action = GetAction()
        result = action.run(actor, target=bare_object)
        assert result.success is False
        assert result.message == "That can't be picked up."


class DropActionTests(TestCase):
    def test_drop_moves_item_to_room(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="Alice", location=room)

        item_obj = ObjectDBFactory(db_key="Sword", location=actor)
        ItemInstanceFactory(game_object=item_obj)

        action = DropAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        item_obj.refresh_from_db()
        assert item_obj.location == room

    def test_drop_auto_unequips_first(self):
        """An equipped item drops cleanly, removing all EquippedItem rows."""
        room = ObjectDBFactory(
            db_key="DropAutoUnequipRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="DropAutoUnequipActor", location=room)

        item_obj = ObjectDBFactory(db_key="DropAutoUnequipShirt", location=actor)
        item_instance = ItemInstanceFactory(game_object=item_obj)
        EquippedItem.objects.create(
            character=actor,
            item_instance=item_instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        action = DropAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        assert not EquippedItem.objects.filter(item_instance=item_instance).exists()
        item_obj.refresh_from_db()
        assert item_obj.location == room


class GiveActionTests(TestCase):
    def test_give_transfers_item_and_writes_ownership_event(self):
        room = ObjectDBFactory(
            db_key="GiveRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        giver_account = AccountFactory(username="give_action_giver")
        recipient_account = AccountFactory(username="give_action_recipient")
        giver = CharacterFactory(db_key="GiveGiver", location=room)
        giver.db_account = giver_account
        giver.save()
        recipient = CharacterFactory(db_key="GiveRecipient", location=room)
        recipient.db_account = recipient_account
        recipient.save()

        item_obj = ObjectDBFactory(db_key="GiveItem", location=giver)
        item_instance = ItemInstanceFactory(game_object=item_obj, owner=giver_account)

        action = GiveAction()
        with patch.object(room, "msg_contents"), patch.object(recipient, "msg"):
            result = action.run(giver, target=item_obj, recipient=recipient)

        assert result.success is True
        item_obj.refresh_from_db()
        assert item_obj.location == recipient

        item_instance.refresh_from_db()
        assert item_instance.owner == recipient_account

        event = OwnershipEvent.objects.get(item_instance=item_instance)
        assert event.event_type == OwnershipEventType.GIVEN
        assert event.from_account == giver_account
        assert event.to_account == recipient_account

    def test_give_without_item_instance_fails_gracefully(self):
        room = ObjectDBFactory(
            db_key="GiveRoomNoInstance",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        giver = CharacterFactory(db_key="GiveGiverNoInstance", location=room)
        recipient = CharacterFactory(db_key="GiveRecipientNoInstance", location=room)
        bare_object = ObjectDBFactory(db_key="GiveBareObject", location=giver)

        action = GiveAction()
        result = action.run(giver, target=bare_object, recipient=recipient)
        assert result.success is False
        assert result.message == "That can't be given."


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
            target_object=self.exit_obj,
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
