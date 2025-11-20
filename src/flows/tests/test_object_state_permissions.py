from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.factories import SceneDataManagerFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.exit_state import ExitState
from flows.object_states.room_state import RoomState


class ObjectStatePermissionTests(TestCase):
    def setUp(self):
        self.context = SceneDataManagerFactory()
        self.room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.dest = ObjectDBFactory(
            db_key="outside",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.exit = ObjectDBFactory(
            db_key="out",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
            destination=self.dest,
        )
        self.item = ObjectDBFactory(db_key="rock", location=self.room)
        for obj in (self.room, self.dest, self.exit, self.char, self.item):
            self.context.initialize_state_for_object(obj)

    def test_default_state_allows_moving_items(self):
        item_state = self.context.get_state_by_pk(self.item.pk)
        actor_state = self.context.get_state_by_pk(self.char.pk)
        dest_state = self.context.get_state_by_pk(self.dest.pk)
        assert item_state.can_move(actor_state, dest_state)

    def test_room_and_exit_cannot_move(self):
        room_state: RoomState = self.context.get_state_by_pk(self.room.pk)
        exit_state: ExitState = self.context.get_state_by_pk(self.exit.pk)
        actor_state = self.context.get_state_by_pk(self.char.pk)
        dest_state = self.context.get_state_by_pk(self.dest.pk)
        assert not room_state.can_move(actor_state, dest_state)
        assert not exit_state.can_move(actor_state, dest_state)

    def test_character_can_move_themselves(self):
        char_state: CharacterState = self.context.get_state_by_pk(self.char.pk)
        dest_state = self.context.get_state_by_pk(self.dest.pk)
        assert char_state.can_move(char_state, dest_state)

    def test_character_cannot_be_moved_by_others(self):
        char_state: CharacterState = self.context.get_state_by_pk(self.char.pk)
        actor_state = self.context.get_state_by_pk(self.item.pk)
        dest_state = self.context.get_state_by_pk(self.dest.pk)
        assert not char_state.can_move(actor_state, dest_state)

    def test_object_cannot_move_into_itself(self):
        item_state = self.context.get_state_by_pk(self.item.pk)
        assert not item_state.can_move(item_state, item_state)
