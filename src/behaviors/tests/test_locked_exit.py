from django.test import TestCase

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory
from flows.factories import SceneDataManagerFactory
from flows.object_states.exit_state import ExitState
import pytest


class LockedExitTests(TestCase):
    def setUp(self):
        self.context = SceneDataManagerFactory()
        self.room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.dest = ObjectDBFactory(
            db_key="yard",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.exit = ObjectDBFactory(
            db_key="out",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
            destination=self.dest,
        )
        self.char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.key = ObjectDBFactory(db_key="silver key", location=self.room)

        self.lock_def = BehaviorPackageDefinition.objects.create(
            name="locked_exit",
            service_function_path="behaviors.matching_value_package.require_matching_value",
        )
        self.key_def = BehaviorPackageDefinition.objects.create(
            name="key",
            service_function_path="behaviors.state_values_package.initialize_state",
        )
        BehaviorPackageInstance.objects.create(
            definition=self.lock_def,
            obj=self.exit,
            hook="can_traverse",
            data={"attribute": "key_id", "value": "silver"},
        )
        BehaviorPackageInstance.objects.create(
            definition=self.key_def,
            obj=self.key,
            hook="initialize_state",
            data={"values": {"key_id": "silver"}},
        )

        for obj in (self.room, self.dest, self.exit, self.char, self.key):
            self.context.initialize_state_for_object(obj)

        self.exit_state: ExitState = self.context.get_state_by_pk(self.exit.pk)
        self.char_state = self.context.get_state_by_pk(self.char.pk)

    def test_key_allows_traversal(self):
        # Initially the key is on the ground; traversal should fail.
        with pytest.raises(CommandError):
            self.exit_state.can_traverse(self.char_state)

        # Give the key to the character and reinitialize its state.
        self.key.location = self.char
        self.context.initialize_state_for_object(self.key)

        assert self.exit_state.can_traverse(self.char_state)
