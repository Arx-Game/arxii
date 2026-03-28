from django.test import TestCase

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from evennia_extensions.factories import ObjectDBFactory
from flows.factories import SceneDataManagerFactory
from flows.object_states.exit_state import ExitState
from flows.service_functions.packages import register_behavior_package, remove_behavior_package


def dummy_hook(**kwargs: object) -> None:
    """No-op hook for service function tests."""


class BehaviorPackageTests(TestCase):
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
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )

    def test_packages_affect_state(self):
        blocker_def = BehaviorPackageDefinition.objects.create(
            name="blocker",
            service_function_path="behaviors.tests.blocker_package.require_matching_value",
        )
        buff_init = BehaviorPackageDefinition.objects.create(
            name="buff_init",
            service_function_path="behaviors.tests.buff_package.initialize_state",
        )
        buff_mod = BehaviorPackageDefinition.objects.create(
            name="buff_mod",
            service_function_path="behaviors.tests.buff_package.modify_strength",
        )
        BehaviorPackageInstance.objects.create(
            definition=blocker_def,
            obj=self.exit,
            hook="can_traverse",
        )
        BehaviorPackageInstance.objects.create(
            definition=buff_init,
            obj=self.char,
            hook="initialize_state",
            data={"bonus": 5},
        )
        BehaviorPackageInstance.objects.create(
            definition=buff_mod,
            obj=self.char,
            hook="modify_strength",
            data={"bonus": 5},
        )

        for obj in (self.room, self.dest, self.exit, self.char):
            self.context.initialize_state_for_object(obj)

        exit_state: ExitState = self.context.get_state_by_pk(self.exit.pk)
        char_state = self.context.get_state_by_pk(self.char.pk)

        assert not exit_state.can_traverse(char_state)
        assert char_state.apply_attribute_modifiers("strength", 10) == 15


class PackageServiceFunctionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.definition = BehaviorPackageDefinition.objects.create(
            name="test_svc_pkg",
            service_function_path="behaviors.tests.test_packages.dummy_hook",
        )

    def setUp(self) -> None:
        self.room = ObjectDBFactory()
        self.scene_data = SceneDataManagerFactory()
        self.scene_data.initialize_state_for_object(self.room)
        self.state = self.scene_data.get_state_by_pk(self.room.pk)

    def test_register_creates_instance(self) -> None:
        register_behavior_package(self.state, self.definition.pk, hook="on_enter")
        assert BehaviorPackageInstance.objects.filter(
            definition=self.definition,
            obj=self.room,
        ).exists()

    def test_register_unknown_pk_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            register_behavior_package(self.state, 99999, hook="on_enter")

    def test_remove_deletes_instance(self) -> None:
        BehaviorPackageInstance.objects.create(
            definition=self.definition,
            obj=self.room,
            hook="on_enter",
            data={},
        )
        remove_behavior_package(self.state, self.definition.pk)
        assert not BehaviorPackageInstance.objects.filter(
            definition=self.definition,
            obj=self.room,
        ).exists()

    def test_remove_nonexistent_is_noop(self) -> None:
        remove_behavior_package(self.state, self.definition.pk)  # no error
