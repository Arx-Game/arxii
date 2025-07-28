from django.test import TestCase

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from evennia_extensions.factories import ObjectDBFactory
from flows.factories import SceneDataManagerFactory
from flows.object_states.exit_state import ExitState


class BehaviorPackageTests(TestCase):
    def setUp(self):
        self.context = SceneDataManagerFactory()
        self.room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.dest = ObjectDBFactory(
            db_key="yard", db_typeclass_path="typeclasses.rooms.Room"
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
            service_function_path="behaviors.tests.blocker_package",
        )
        buff_def = BehaviorPackageDefinition.objects.create(
            name="buff",
            service_function_path="behaviors.tests.buff_package",
        )
        BehaviorPackageInstance.objects.create(definition=blocker_def, obj=self.exit)
        BehaviorPackageInstance.objects.create(
            definition=buff_def, obj=self.char, data={"bonus": 5}
        )

        for obj in (self.room, self.dest, self.exit, self.char):
            self.context.initialize_state_for_object(obj)

        exit_state: ExitState = self.context.get_state_by_pk(self.exit.pk)
        char_state = self.context.get_state_by_pk(self.char.pk)

        self.assertFalse(exit_state.can_traverse(char_state))
        self.assertEqual(char_state.apply_attribute_modifiers("strength", 10), 15)
