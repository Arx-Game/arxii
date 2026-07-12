"""Tests for concrete action implementations."""

from unittest.mock import patch

from django.test import TestCase, tag

from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from actions.definitions.movement import (
    DropAction,
    GetAction,
    GiveAction,
    StopTravelAction,
    TravelAction,
    TraverseExitAction,
)
from actions.definitions.perception import InventoryAction, LookAction
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from evennia_extensions.models import RoomProfile
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.items.constants import BodyRegion, EquipmentLayer, OwnershipEventType
from world.items.factories import ItemInstanceFactory
from world.items.models import EquippedItem, OwnershipEvent
from world.magic.factories import (
    CharacterTechniqueFactory,
    PortalAnchorFactory,
    PortalAnchorKindFactory,
    TechniqueFactory,
)
from world.mechanics.constants import ChallengeType
from world.mechanics.factories import ChallengeTemplateFactory
from world.mechanics.models import ChallengeInstance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


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


class LookActionConcealmentTests(TestCase):
    """Telnet parity for #1225 — ``get_display_characters`` gates on ``can_perceive``.

    ``LookAction.execute`` threads ``actor`` through as the ``looker`` so the room's
    ``Characters:`` line matches the web room-state gate.
    """

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="dim hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.actor_sheet = RosterEntryFactory().character_sheet
        self.actor = self.actor_sheet.character
        self.actor.location = self.room

        self.visible = CharacterFactory(db_key="Ally", location=self.room)
        self.concealed = CharacterFactory(db_key="Shade", location=self.room)

        cat = ConditionCategoryFactory(conceals_from_perception=True)
        self.concealing_condition = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.concealed, condition=self.concealing_condition)

    def test_concealed_and_undetected_character_omitted_from_room_look(self):
        result = LookAction().run(self.actor, target=self.room)
        assert "Ally" in result.message
        assert "Shade" not in result.message

    def test_detected_concealed_character_appears_in_room_look(self):
        register_detection(self.actor_sheet, self.concealed)

        result = LookAction().run(self.actor, target=self.room)
        assert "Shade" in result.message

    def test_looker_always_sees_themselves_even_if_concealed(self):
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.actor, condition=template)

        result = LookAction().run(self.actor, target=self.room)
        # The room's own "Characters:" line lists everyone else present, but the
        # looker's own concealment must never make the room itself unreadable.
        assert result.success is True

    def test_direct_look_at_concealed_and_undetected_character_fails_generic(self):
        """Bypassing the room list by naming the target directly must still be
        blocked (#1225 review gap) — and with the same not-found idiom the
        genuinely-absent case uses, so the two are indistinguishable."""
        result = LookAction().run(self.actor, target=self.concealed)
        assert result.success is False
        assert result.message == f"Could not find '{self.concealed.key}'."

    def test_direct_look_at_detected_concealed_character_succeeds(self):
        register_detection(self.actor_sheet, self.concealed)

        result = LookAction().run(self.actor, target=self.concealed)
        assert result.success is True

    def test_direct_look_at_unconcealed_character_unaffected(self):
        result = LookAction().run(self.actor, target=self.visible)
        assert result.success is True

    def test_bare_room_look_not_gated_by_new_check(self):
        """No-args ``look`` resolves target to the room itself — the new gate
        must never apply ``can_perceive`` to the room container, which would
        incorrectly return False (rooms aren't occupants/held items)."""
        result = LookAction().run(self.actor, target=self.room)
        assert result.success is True


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


class PemitActionTests(TestCase):
    """GM private narrative emit, gated on STARTING-tier GM trust or staff (#906/#2117)."""

    def _staff_actor(self, room):
        account = AccountFactory(username="pemit_staff", is_staff=True)
        actor = ObjectDBFactory(
            db_key="GM",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        actor.db_account = account
        actor.save()
        return actor

    def _gm_actor(self, room, level, *, db_key="TrustGM"):
        """Return a Character with a live roster tenure + GMProfile at ``level``."""
        actor = ObjectDBFactory(
            db_key=db_key,
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        CharacterSheetFactory(character=actor)
        entry = RosterEntryFactory(character_sheet__character=actor)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        GMProfileFactory(account=tenure.player_data.account, level=level)
        return actor

    def test_pemit_delivers_to_receivers_only(self):
        from actions.definitions.communication import PemitAction

        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = self._staff_actor(room)
        receiver = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        CharacterSheetFactory(character=receiver)
        bystander = ObjectDBFactory(
            db_key="Eve",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        action = PemitAction()
        with (
            patch.object(receiver, "msg") as recv_msg,
            patch.object(bystander, "msg") as bystander_msg,
        ):
            result = action.run(actor, receivers=[receiver], text="A chill wind finds you.")
        assert result.success is True
        recv_msg.assert_called_once()
        bystander_msg.assert_not_called()

    def test_pemit_rejects_non_staff_non_gm(self):
        from actions.definitions.communication import PemitAction

        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="pemit_player", is_staff=False)
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        actor.db_account = account
        actor.save()
        receiver = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        action = PemitAction()
        result = action.run(actor, receivers=[receiver], text="sneaky")
        assert result.success is False
        assert "GM trust required." in result.message

    def test_pemit_availability_requires_gm_trust(self):
        from actions.definitions.communication import PemitAction

        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="pemit_player2", is_staff=False)
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        actor.db_account = account
        actor.save()
        availability = PemitAction().check_availability(actor)
        assert availability.available is False

    def test_pemit_starting_gm_succeeds(self):
        """A STARTING-tier GM (no staff flag) may pemit (#2117)."""
        from actions.definitions.communication import PemitAction

        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = self._gm_actor(room, GMLevel.STARTING)
        receiver = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        CharacterSheetFactory(character=receiver)
        with patch.object(receiver, "msg"):
            result = PemitAction().run(actor, receivers=[receiver], text="A whisper of magic.")
        assert result.success is True

    def test_pemit_without_receivers_fails(self):
        from actions.definitions.communication import PemitAction

        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = self._staff_actor(room)
        result = PemitAction().run(actor, receivers=[], text="to no one")
        assert result.success is False

    def test_pemit_without_text_fails(self):
        from actions.definitions.communication import PemitAction

        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = self._staff_actor(room)
        receiver = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        result = PemitAction().run(actor, receivers=[receiver], text="")
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
        actor_sheet = CharacterSheetFactory(character=actor)

        item_obj = ObjectDBFactory(db_key="Sword", location=room)
        item_instance = ItemInstanceFactory(game_object=item_obj)

        action = GetAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        item_obj.refresh_from_db()
        assert item_obj.location == actor

        # #684: Pick-up sets the holder body (CharacterSheet) when previously unowned.
        item_instance.refresh_from_db()
        assert item_instance.holder_character_sheet == actor_sheet

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
        giver_sheet = CharacterSheetFactory(character=giver)
        recipient = CharacterFactory(db_key="GiveRecipient", location=room)
        recipient.db_account = recipient_account
        recipient.save()
        recipient_sheet = CharacterSheetFactory(character=recipient)

        item_obj = ObjectDBFactory(db_key="GiveItem", location=giver)
        item_instance = ItemInstanceFactory(
            game_object=item_obj, holder_character_sheet=giver_sheet
        )

        action = GiveAction()
        with patch.object(room, "msg_contents"), patch.object(recipient, "msg"):
            result = action.run(giver, target=item_obj, recipient=recipient)

        assert result.success is True
        item_obj.refresh_from_db()
        assert item_obj.location == recipient

        item_instance.refresh_from_db()
        # #684: holder is the recipient's body, not their account.
        assert item_instance.holder_character_sheet == recipient_sheet

        event = OwnershipEvent.objects.get(item_instance=item_instance)
        assert event.event_type == OwnershipEventType.GIVEN
        assert event.from_character_sheet == giver_sheet
        assert event.to_character_sheet == recipient_sheet

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


class TravelActionTests(TestCase):
    def _make_route(self, hop_count):
        """origin -> room_1 -> ... -> room_N, each room public, same Area."""
        area = AreaFactory()
        rooms = []
        for i in range(hop_count + 1):
            room = ObjectDBFactory(
                db_key=f"TravelRoom{i}",
                db_typeclass_path="typeclasses.rooms.Room",
            )
            # typeclasses.rooms.Room.at_object_creation() already auto-creates a
            # bare RoomProfile via get_or_create — update_or_create (not create)
            # applies our area/is_public onto that existing row instead of
            # colliding with it (same gotcha documented in Task 1's
            # world/areas/positioning/tests/test_travel.py:make_room).
            RoomProfile.objects.update_or_create(
                objectdb=room, defaults={"area": area, "is_public": True}
            )
            rooms.append(room)
        exits = [
            ObjectDBFactory(
                db_key=f"exit{i}",
                db_typeclass_path="typeclasses.exits.Exit",
                location=rooms[i],
                destination=rooms[i + 1],
            )
            for i in range(hop_count)
        ]
        return rooms, exits

    @tag("postgres")  # a successful hop calls send_room_state -> get_ancestry,
    # which walks the areas_areaclosure materialized view (PG-only).
    def test_travel_walks_full_route_and_arrives(self):
        rooms, _exits = self._make_route(3)
        actor = ObjectDBFactory(
            db_key="Traveler",
            db_typeclass_path="typeclasses.characters.Character",
            location=rooms[0],
        )
        action = TravelAction()

        with patch.object(actor, "msg"), patch("actions.definitions.movement.delay") as mock_delay:
            # Capture-and-run: TravelAction schedules its next hop via
            # evennia.utils.delay(seconds, callback, ...) — since this test
            # runs synchronously (no real reactor), replace delay with an
            # immediate call to the callback so the whole route walks in
            # one test tick. This exercises the exact same callback logic
            # the real delayed path uses, just without the real pause.
            def run_immediately(_seconds, callback, *args, **kwargs):
                callback(*args, **kwargs)

            mock_delay.side_effect = run_immediately
            result = action.run(actor, target=rooms[-1])

        assert result.success is True
        actor.refresh_from_db()
        assert actor.location == rooms[-1]
        assert actor.ndb.active_travel_token is None

    @tag("postgres")  # a successful hop calls send_room_state -> get_ancestry,
    # which walks the areas_areaclosure materialized view (PG-only).
    def test_travel_crosses_area_boundary_and_arrives(self):
        """#2223 action-seam test: origin and destination live in different
        Areas joined by a boundary exit — TravelAction.run() must walk the
        route across the boundary exactly like a same-Area walk (mirrors
        world/areas/positioning/tests/test_travel.py's
        test_multi_hop_route_crosses_boundary_partway, but dispatched through
        the action.run() seam instead of calling find_route() directly).
        """
        area = AreaFactory()
        other_area = AreaFactory()
        room_a = ObjectDBFactory(db_key="CrossAreaA", db_typeclass_path="typeclasses.rooms.Room")
        room_boundary = ObjectDBFactory(
            db_key="CrossAreaBoundary", db_typeclass_path="typeclasses.rooms.Room"
        )
        room_c = ObjectDBFactory(db_key="CrossAreaC", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room_a, defaults={"area": area, "is_public": True}
        )
        RoomProfile.objects.update_or_create(
            objectdb=room_boundary, defaults={"area": area, "is_public": True}
        )
        RoomProfile.objects.update_or_create(
            objectdb=room_c, defaults={"area": other_area, "is_public": True}
        )
        ObjectDBFactory(
            db_key="exit_a_boundary",
            db_typeclass_path="typeclasses.exits.Exit",
            location=room_a,
            destination=room_boundary,
        )
        ObjectDBFactory(
            db_key="exit_boundary_c",
            db_typeclass_path="typeclasses.exits.Exit",
            location=room_boundary,
            destination=room_c,
        )
        actor = ObjectDBFactory(
            db_key="CrossAreaTraveler",
            db_typeclass_path="typeclasses.characters.Character",
            location=room_a,
        )
        action = TravelAction()

        with patch.object(actor, "msg"), patch("actions.definitions.movement.delay") as mock_delay:

            def run_immediately(_seconds, callback, *args, **kwargs):
                callback(*args, **kwargs)

            mock_delay.side_effect = run_immediately
            result = action.run(actor, target=room_c)

        assert result.success is True
        actor.refresh_from_db()
        assert actor.location == room_c
        assert actor.ndb.active_travel_token is None

    def test_travel_no_route_fails_immediately(self):
        area = AreaFactory()
        room_a = ObjectDBFactory(db_key="A", db_typeclass_path="typeclasses.rooms.Room")
        room_b = ObjectDBFactory(db_key="B", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room_a, defaults={"area": area, "is_public": True}
        )
        RoomProfile.objects.update_or_create(
            objectdb=room_b, defaults={"area": area, "is_public": True}
        )
        # No exit connects them.
        actor = ObjectDBFactory(
            db_key="Stuck",
            db_typeclass_path="typeclasses.characters.Character",
            location=room_a,
        )
        action = TravelAction()

        result = action.run(actor, target=room_b)

        assert result.success is False
        assert actor.location == room_a

    @tag("postgres")  # hop 1 succeeds and calls send_room_state -> get_ancestry,
    # which walks the areas_areaclosure materialized view (PG-only).
    def test_travel_stops_early_when_a_waypoint_goes_private_mid_walk(self):
        rooms, _exits = self._make_route(2)
        actor = ObjectDBFactory(
            db_key="Traveler2",
            db_typeclass_path="typeclasses.characters.Character",
            location=rooms[0],
        )
        action = TravelAction()

        hop_count = {"n": 0}

        def run_and_flip_privacy(_seconds, callback, *args, **kwargs):
            hop_count["n"] += 1
            if hop_count["n"] == 2:
                # Simulate a GM flipping the final waypoint private between
                # dispatch and this hop's execution.
                rooms[2].room_profile.is_public = False
                rooms[2].room_profile.save()
            callback(*args, **kwargs)

        with (
            patch.object(actor, "msg"),
            patch("actions.definitions.movement.delay", side_effect=run_and_flip_privacy),
        ):
            action.run(actor, target=rooms[-1])

        actor.refresh_from_db()
        # Stopped at the last successfully-reached room, never entered the
        # now-private room 2.
        assert actor.location == rooms[1]
        assert actor.ndb.active_travel_token is None

    def test_stop_travel_clears_active_token(self):
        rooms, _exits = self._make_route(3)
        actor = ObjectDBFactory(
            db_key="Traveler3",
            db_typeclass_path="typeclasses.characters.Character",
            location=rooms[0],
        )
        with patch.object(actor, "msg"), patch("actions.definitions.movement.delay") as mock_delay:
            # Don't run the callback — leave the walk "in flight".
            mock_delay.return_value = None
            TravelAction().run(actor, target=rooms[-1])

        assert actor.ndb.active_travel_token is not None

        with patch.object(actor, "msg"):
            result = StopTravelAction().run(actor)

        assert result.success is True
        assert actor.ndb.active_travel_token is None
        # Actor never actually moved past the origin (walk was stopped
        # before any hop callback fired).
        actor.refresh_from_db()
        assert actor.location == rooms[0]

    def test_redispatch_supersedes_prior_walk_no_orphaned_movement(self):
        rooms, _exits = self._make_route(3)
        actor = ObjectDBFactory(
            db_key="Traveler4",
            db_typeclass_path="typeclasses.characters.Character",
            location=rooms[0],
        )
        stale_callbacks = []

        def capture_but_dont_run(_seconds, callback, *args, **kwargs):
            stale_callbacks.append((callback, args, kwargs))

        with (
            patch.object(actor, "msg"),
            patch("actions.definitions.movement.delay", side_effect=capture_but_dont_run),
        ):
            TravelAction().run(actor, target=rooms[-1])
            first_token = actor.ndb.active_travel_token

            # Re-dispatch mid-walk — supersedes the first walk.
            TravelAction().run(actor, target=rooms[1])
            second_token = actor.ndb.active_travel_token

        assert first_token != second_token

        # Now fire the STALE callback from the first walk (as if its delay
        # had actually elapsed after being superseded) — it must no-op.
        stale_callback, stale_args, stale_kwargs = stale_callbacks[0]
        with patch.object(actor, "msg"):
            stale_callback(*stale_args, **stale_kwargs)

        actor.refresh_from_db()
        # The stale callback did NOT move the actor — token mismatch caught it.
        assert actor.location == rooms[0]

    @tag("postgres")  # a successful hop calls send_room_state -> get_ancestry,
    # which walks the areas_areaclosure materialized view (PG-only).
    def test_travel_resolves_int_target_like_a_rest_dispatch_would(self):
        """Regression test for the web dispatch path (#2163 final-review Critical
        finding): REST dispatch (`_dispatch_registry`) does NOT resolve
        objectdb_target_kwargs — it passes kwargs straight to execute(). This test
        calls TravelAction exactly as the REST path does: target as a raw int, not
        a pre-resolved ObjectDB, mirroring what `dispatch_player_action` /
        `_dispatch_registry` actually does (see `src/actions/player_interface.py`).
        """
        rooms, _exits = self._make_route(2)
        actor = ObjectDBFactory(
            db_key="RestTraveler",
            db_typeclass_path="typeclasses.characters.Character",
            location=rooms[0],
        )
        action = TravelAction()

        with patch.object(actor, "msg"), patch("actions.definitions.movement.delay") as mock_delay:

            def run_immediately(_seconds, callback, *args, **kwargs):
                callback(*args, **kwargs)

            mock_delay.side_effect = run_immediately
            # target is a plain int, exactly as it arrives from a REST dispatch's
            # raw JSON kwargs — NOT rooms[-1] (the ObjectDB), which is what a
            # telnet .run() call would pass.
            result = action.run(actor, target=rooms[-1].id)

        assert result.success is True
        actor.refresh_from_db()
        assert actor.location == rooms[-1]

    def test_travel_int_target_that_does_not_exist_fails_gracefully(self):
        area = AreaFactory()
        room_a = ObjectDBFactory(db_key="OnlyRoom", db_typeclass_path="typeclasses.rooms.Room")
        # typeclasses.rooms.Room.at_object_creation() already auto-creates a bare
        # RoomProfile via get_or_create — update_or_create (not create) applies
        # our area/is_public onto that existing row instead of colliding with it
        # (same gotcha documented in _make_route above).
        RoomProfile.objects.update_or_create(
            objectdb=room_a, defaults={"area": area, "is_public": True}
        )
        actor = ObjectDBFactory(
            db_key="LostTraveler",
            db_typeclass_path="typeclasses.characters.Character",
            location=room_a,
        )
        action = TravelAction()

        result = action.run(actor, target=999999999)

        assert result.success is False
        actor.refresh_from_db()
        assert actor.location == room_a


class PortalTravelTests(TestCase):
    """#2222 — TravelAction's portal branch, tried before the walking pathfinder.

    The branch is tried FIRST inside execute() (after the raw-int destination
    resolution); on a portal_route() hit it relocates instantly via
    perform_portal_travel and returns without ever touching find_route or
    scheduling a hop via evennia.utils.delay(). On a miss it falls through to
    the pre-existing walking path, byte-identical to before this issue.
    """

    @staticmethod
    def _make_room(key):
        room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
        room_profile = RoomProfileFactory(objectdb=room)
        return room, room_profile

    @staticmethod
    def _make_traveler(location, *, technique=None):
        actor = CharacterFactory(location=location)
        sheet = CharacterSheetFactory(character=actor)
        if technique is not None:
            CharacterTechniqueFactory(character=sheet, technique=technique)
        return actor

    @tag("postgres")  # perform_portal_travel calls send_room_state -> get_ancestry,
    # which walks the areas_areaclosure materialized view (PG-only).
    def test_portal_eligible_travel_relocates_instantly_no_hop_pacing(self):
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind, anima_cost=0)
        origin, origin_rp = self._make_room("Origin Mirror Room")
        dest, dest_rp = self._make_room("Dest Mirror Room")
        PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        PortalAnchorFactory(room_profile=dest_rp, kind=kind)
        actor = self._make_traveler(origin, technique=technique)
        action = TravelAction()

        with (
            patch.object(actor, "msg"),
            patch("actions.definitions.movement.delay") as mock_delay,
        ):
            result = action.run(actor, target=dest)

        assert result.success is True
        actor.refresh_from_db()
        assert actor.location == dest
        # No hop pacing at all — the portal branch never calls find_route or
        # schedules a delayed hop, unlike the walking path.
        mock_delay.assert_not_called()
        assert actor.ndb.active_travel_token is None

    @tag("postgres")  # a successful hop calls send_room_state -> get_ancestry (PG-only).
    def test_no_known_technique_falls_back_to_walking(self):
        """Anchors exist at both ends, but the traveler knows no portal-travel
        technique — portal_route() returns None and the walking path
        (paced hop via evennia.utils.delay) runs exactly as it did pre-#2222.
        """
        area = AreaFactory()
        kind = PortalAnchorKindFactory()
        origin, origin_rp = self._make_room("Walk Origin")
        dest, dest_rp = self._make_room("Walk Dest")
        # Instance-attribute save, NOT queryset.update() — a raw UPDATE bypasses
        # the SharedMemoryModel identity map, leaving the cached RoomProfile
        # stale (area=None) so find_route would see a non-public, area-less room
        # and the walk would fail (caught on the PG parity run of this test).
        for room_profile in (origin_rp, dest_rp):
            room_profile.area = area
            room_profile.is_public = True
            room_profile.save()
        PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        PortalAnchorFactory(room_profile=dest_rp, kind=kind)
        ObjectDBFactory(
            db_key="walk-exit",
            db_typeclass_path="typeclasses.exits.Exit",
            location=origin,
            destination=dest,
        )
        actor = self._make_traveler(origin)  # no known technique

        with patch.object(actor, "msg"), patch("actions.definitions.movement.delay") as mock_delay:

            def run_immediately(_seconds, callback, *args, **kwargs):
                callback(*args, **kwargs)

            mock_delay.side_effect = run_immediately
            result = TravelAction().run(actor, target=dest)

        assert result.success is True
        mock_delay.assert_called()  # the walking path paced at least one hop
        actor.refresh_from_db()
        assert actor.location == dest

    @tag("postgres")  # perform_portal_travel calls send_room_state -> get_ancestry (PG-only).
    def test_portal_eligible_rest_raw_int_destination_works(self):
        """REST dispatch (`_dispatch_registry`) passes kwargs straight to
        execute() — `target` arrives as a raw int, not a pre-resolved
        ObjectDB (#2163 gotcha). The portal branch must handle this exactly
        like TravelAction's own pre-existing int-resolution.
        """
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind, anima_cost=0)
        origin, origin_rp = self._make_room("REST Origin")
        dest, dest_rp = self._make_room("REST Dest")
        PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        PortalAnchorFactory(room_profile=dest_rp, kind=kind)
        actor = self._make_traveler(origin, technique=technique)
        action = TravelAction()

        with patch.object(actor, "msg"), patch("actions.definitions.movement.delay") as mock_delay:
            # target is a plain int, exactly as it arrives from a REST dispatch's
            # raw JSON kwargs — NOT dest (the ObjectDB).
            result = action.run(actor, target=dest.id)

        assert result.success is True
        actor.refresh_from_db()
        assert actor.location == dest
        mock_delay.assert_not_called()


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
