"""Tests for the servant-fetch service (#2276).

The AreaClosure materialized view is Postgres-only, so tests that would
hit the closure chain mock ``is_owner``/``is_tenant``/``find_servant``
at the service boundary rather than relying on real closure data.
"""

from unittest.mock import patch
import uuid

from django.test import TestCase

from evennia_extensions.factories import (
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemInstanceFactory,
    OutfitFactory,
    OutfitSlotFactory,
)
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.models import (
    AssignmentRole,
    NPCAssignment,
    NPCSourceType,
)
from world.npc_services.servant_fetch import (
    can_servant_fetch,
    cancel_servant_fetch,
    find_servant,
    servant_fetch_item,
    servant_fetch_outfit,
)
from world.scenes.factories import PersonaFactory


def _make_item_in_room(room):
    """Create an ItemInstance with a game_object placed in ``room``."""
    obj = ObjectDBFactory(db_key="item-obj")
    obj.location = room
    obj.save()
    return ItemInstanceFactory(game_object=obj)


class FindServantTests(TestCase):
    """Tests for find_servant.

    The AreaClosure materialized view is Postgres-only, so we mock the
    closure query and test the NPCAssignment filtering logic directly.
    """

    def setUp(self) -> None:
        self.area = AreaFactory()
        self.room_profile = RoomProfileFactory(area=self.area)
        self.room = self.room_profile.objectdb

    def _create_servant(self, room_profile=None):
        """Create an active SERVANT NPCAssignment in a room."""
        func = FunctionaryFactory(room=room_profile or self.room_profile)
        persona = PersonaFactory()
        return NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=room_profile or self.room_profile,
            assignment_role=AssignmentRole.SERVANT,
            assigned_by=persona,
        )

    def test_no_servant_returns_none(self):
        """Room with no SERVANT assignment → None."""
        with patch(
            "world.areas.models.AreaClosure",
        ) as mock_closure:
            mock_closure.objects.filter.return_value.values_list.return_value = [self.area.pk]
            self.assertIsNone(find_servant(self.room))

    def test_servant_in_same_room_found(self):
        """SERVANT assigned to the actor's room → found."""
        self._create_servant()
        # Patch AreaClosure to return the area's own pk (self at depth 0).
        with patch(
            "world.areas.models.AreaClosure",
        ) as mock_closure:
            mock_closure.objects.filter.return_value.values_list.return_value = [self.area.pk]
            result = find_servant(self.room)
        self.assertIsNotNone(result)
        self.assertEqual(result.assignment_role, AssignmentRole.SERVANT)

    def test_inactive_servant_not_found(self):
        """Retired SERVANT → not found."""
        assignment = self._create_servant()
        assignment.is_active = False
        assignment.save()
        with patch(
            "world.areas.models.AreaClosure",
        ) as mock_closure:
            mock_closure.objects.filter.return_value.values_list.return_value = [self.area.pk]
            result = find_servant(self.room)
        self.assertIsNone(result)

    def test_guard_not_treated_as_servant(self):
        """A GUARD assignment does not satisfy find_servant."""
        func = FunctionaryFactory(room=self.room_profile)
        NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        with patch(
            "world.areas.models.AreaClosure",
        ) as mock_closure:
            mock_closure.objects.filter.return_value.values_list.return_value = [self.area.pk]
            result = find_servant(self.room)
        self.assertIsNone(result)

    def test_no_profile_returns_none(self):
        """Room with no RoomProfile → None."""
        from evennia.objects.models import ObjectDB

        bare_room = ObjectDB.objects.create(db_key="bare-room")
        self.assertIsNone(find_servant(bare_room))


class CanServantFetchTests(TestCase):
    """Tests for can_servant_fetch.

    Mocks ``is_owner``/``is_tenant``/``find_servant`` since they hit
    the Postgres-only AreaClosure view.
    """

    def setUp(self) -> None:
        self.area = AreaFactory()
        self.room_profile = RoomProfileFactory(area=self.area)
        self.room = self.room_profile.objectdb
        self.other_room_profile = RoomProfileFactory(area=self.area)
        self.other_room = self.other_room_profile.objectdb
        self.owner_persona = PersonaFactory()
        self.char = CharacterFactory(db_key="owner")
        CharacterSheetFactory(character=self.char)
        self.char.location = self.room
        self.char.save()
        # Item in the other room.
        self.item_instance = _make_item_in_room(self.other_room)
        # Servant assignment (for find_servant to return).
        func = FunctionaryFactory(room=self.room_profile)
        self.servant = NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.SERVANT,
            assigned_by=self.owner_persona,
        )

    def test_eligible_when_owner_with_servant_and_item_in_other_room(self):
        """Owner + servant + item in another room → True."""
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertTrue(can_servant_fetch(actor=self.char, item_instance=self.item_instance))

    def test_no_servant_returns_false(self):
        """Owner but no servant → False."""
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=None,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertFalse(can_servant_fetch(actor=self.char, item_instance=self.item_instance))

    def test_same_room_item_returns_false(self):
        """Item in the same room (closed container case) → False."""
        # Move item to the actor's room (same room).
        self.item_instance.game_object.location = self.room
        self.item_instance.game_object.save()
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertFalse(can_servant_fetch(actor=self.char, item_instance=self.item_instance))

    def test_no_standing_returns_false(self):
        """Actor without owner/tenant standing → False."""
        with (
            patch("world.locations.services.is_owner", return_value=False),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertFalse(can_servant_fetch(actor=self.char, item_instance=self.item_instance))

    def test_no_game_object_returns_false(self):
        """Item with no game_object → False."""
        no_game_obj = ItemInstanceFactory()
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertFalse(can_servant_fetch(actor=self.char, item_instance=no_game_obj))

    def test_no_persona_returns_false(self):
        """Actor with no active persona → False."""
        with patch(
            "world.scenes.services.active_persona_for_sheet",
            return_value=None,
        ):
            self.assertFalse(can_servant_fetch(actor=self.char, item_instance=self.item_instance))


class ServantFetchItemTests(TestCase):
    """Tests for servant_fetch_item and _complete_item_fetch."""

    def setUp(self) -> None:
        self.area = AreaFactory()
        self.room_profile = RoomProfileFactory(area=self.area)
        self.room = self.room_profile.objectdb
        self.other_room_profile = RoomProfileFactory(area=self.area)
        self.other_room = self.other_room_profile.objectdb
        self.owner_persona = PersonaFactory()
        self.char = CharacterFactory(db_key="fetcher")
        CharacterSheetFactory(character=self.char)
        self.char.location = self.room
        self.char.save()
        # Item in the other room.
        self.item_instance = _make_item_in_room(self.other_room)
        # Servant.
        func = FunctionaryFactory(room=self.room_profile)
        self.servant = NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.SERVANT,
            assigned_by=self.owner_persona,
        )

    def test_fetch_moves_item_to_actor(self):
        """After the delay fires, item is in actor's possession."""
        with (
            patch("world.npc_services.servant_fetch.delay") as mock_delay,
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
        ):
            mock_delay.side_effect = lambda _seconds, callback, *args: callback(*args)
            result = servant_fetch_item(
                actor=self.char, item_instance=self.item_instance, delay_seconds=0
            )
        self.assertTrue(result)
        self.item_instance.refresh_from_db()
        self.assertEqual(self.item_instance.game_object.location, self.char)

    def test_fetch_sets_holder_character_sheet(self):
        """Unowned item gets holder set to the actor's sheet."""
        self.item_instance.holder_character_sheet = None
        self.item_instance.save()
        with (
            patch("world.npc_services.servant_fetch.delay") as mock_delay,
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
        ):
            mock_delay.side_effect = lambda _seconds, callback, *args: callback(*args)
            servant_fetch_item(actor=self.char, item_instance=self.item_instance, delay_seconds=0)
        self.item_instance.refresh_from_db()
        self.assertEqual(self.item_instance.holder_character_sheet, self.char.sheet_data)

    def test_fetch_clears_contained_in(self):
        """Item in a container has contained_in cleared."""
        container = _make_item_in_room(self.other_room)
        self.item_instance.contained_in = container
        self.item_instance.save()
        with (
            patch("world.npc_services.servant_fetch.delay") as mock_delay,
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
        ):
            mock_delay.side_effect = lambda _seconds, callback, *args: callback(*args)
            servant_fetch_item(actor=self.char, item_instance=self.item_instance, delay_seconds=0)
        self.item_instance.refresh_from_db()
        self.assertIsNone(self.item_instance.contained_in)

    def test_fetch_sets_ndb_token(self):
        """Fetch sets the cancellation token on the actor."""
        with (
            patch("world.npc_services.servant_fetch.delay"),
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
        ):
            servant_fetch_item(actor=self.char, item_instance=self.item_instance, delay_seconds=5.0)
        self.assertIsNotNone(self.char.ndb.active_fetch_token)

    def test_stale_callback_no_ops(self):
        """A stale token (actor moved) → no item delivery."""
        with (
            patch("world.npc_services.servant_fetch.delay") as mock_delay,
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=self.servant,
            ),
        ):
            captured = []
            mock_delay.side_effect = lambda _seconds, callback, *args: captured.append(
                (callback, args)
            )
            servant_fetch_item(actor=self.char, item_instance=self.item_instance, delay_seconds=5.0)
            # Simulate the actor moving (token invalidated).
            self.char.ndb.active_fetch_token = uuid.uuid4()
            # Now fire the stale callback.
            callback, args = captured[0]
            callback(*args)

        # Item should NOT have moved.
        self.item_instance.refresh_from_db()
        self.assertEqual(self.item_instance.game_object.location, self.other_room)


class CancelServantFetchTests(TestCase):
    def test_cancel_clears_token_and_task(self):
        from unittest.mock import Mock

        char = CharacterFactory(db_key="mover")
        char.ndb.active_fetch_token = uuid.uuid4()
        mock_task = Mock()
        char.ndb.active_fetch_task = mock_task
        cancel_servant_fetch(char)
        mock_task.cancel.assert_called_once()
        self.assertIsNone(char.ndb.active_fetch_token)
        self.assertIsNone(char.ndb.active_fetch_task)

    def test_cancel_noop_when_no_fetch(self):
        char = CharacterFactory(db_key="idle")
        # Should not raise.
        cancel_servant_fetch(char)
        self.assertIsNone(char.ndb.active_fetch_token)


class ServantFetchOutfitTests(TestCase):
    """Tests for servant_fetch_outfit and _complete_outfit_fetch."""

    def setUp(self) -> None:
        self.area = AreaFactory()
        self.room_profile = RoomProfileFactory(area=self.area)
        self.room = self.room_profile.objectdb
        self.other_room_profile = RoomProfileFactory(area=self.area)
        self.other_room = self.other_room_profile.objectdb
        self.owner_persona = PersonaFactory()
        self.char = CharacterFactory(db_key="noble")
        self.sheet = CharacterSheetFactory(character=self.char)
        self.char.location = self.room
        self.char.save()
        # Wardrobe in the other room.
        self.wardrobe = _make_item_in_room(self.other_room)
        # Outfit piece in the other room (owned by the sheet).
        self.piece = _make_item_in_room(self.other_room)
        self.piece.holder_character_sheet = self.sheet
        self.piece.save()
        # Give the piece's template an equipment slot so equip() can equip it.
        from world.items.factories import TemplateSlotFactory

        TemplateSlotFactory(template=self.piece.template)
        # Outfit referencing the wardrobe + piece.
        self.outfit = OutfitFactory(
            character_sheet=self.sheet, wardrobe=self.wardrobe, name="Court Attire"
        )
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.piece,
        )
        # Servant.
        func = FunctionaryFactory(room=self.room_profile)
        NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.SERVANT,
            assigned_by=self.owner_persona,
        )

    def test_outfit_fetch_equips_pieces(self):
        """After delay, outfit pieces are moved to actor and equipped."""
        from world.items.models import EquippedItem

        with (
            patch("world.npc_services.servant_fetch.delay") as mock_delay,
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=NPCAssignment.objects.filter(
                    assignment_role=AssignmentRole.SERVANT, is_active=True
                ).first(),
            ),
        ):
            mock_delay.side_effect = lambda _seconds, callback, *args: callback(*args)
            result = servant_fetch_outfit(actor=self.char, outfit=self.outfit, delay_seconds=0)
        self.assertTrue(result)
        # The piece should now be on the actor.
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.game_object.location, self.char)
        # And should have an equipped row.
        self.assertTrue(
            EquippedItem.objects.filter(character=self.char, item_instance=self.piece).exists()
        )

    def test_outfit_fetch_stale_callback_no_ops(self):
        """Stale token → no equip, pieces stay in other room."""
        from world.items.models import EquippedItem

        with (
            patch("world.npc_services.servant_fetch.delay") as mock_delay,
            patch(
                "world.npc_services.servant_fetch.find_servant",
                return_value=NPCAssignment.objects.filter(
                    assignment_role=AssignmentRole.SERVANT, is_active=True
                ).first(),
            ),
        ):
            captured = []
            mock_delay.side_effect = lambda _seconds, callback, *args: captured.append(
                (callback, args)
            )
            servant_fetch_outfit(actor=self.char, outfit=self.outfit, delay_seconds=5.0)
            # Simulate actor moving.
            self.char.ndb.active_fetch_token = uuid.uuid4()
            callback, args = captured[0]
            callback(*args)

        self.piece.refresh_from_db()
        self.assertEqual(self.piece.game_object.location, self.other_room)
        self.assertFalse(
            EquippedItem.objects.filter(character=self.char, item_instance=self.piece).exists()
        )
