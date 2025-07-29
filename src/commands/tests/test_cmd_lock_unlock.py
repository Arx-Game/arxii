from unittest.mock import MagicMock

from django.test import TestCase

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from commands.door import CmdLock, CmdUnlock
from evennia_extensions.factories import ObjectDBFactory


class CmdLockUnlockTests(TestCase):
    def setUp(self):
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
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.key = ObjectDBFactory(db_key="silver key", location=self.caller)
        self.caller.msg = MagicMock()
        self.lock_def = BehaviorPackageDefinition.objects.create(
            name="locked_exit",
            service_function_path="behaviors.matching_value_package.require_matching_value",
        )
        self.key_def = BehaviorPackageDefinition.objects.create(
            name="key",
            service_function_path="behaviors.state_values_package.initialize_state",
        )
        BehaviorPackageInstance.objects.create(
            definition=self.key_def,
            obj=self.key,
            hook="initialize_state",
            data={"values": {"key_id": "silver"}},
        )

    def test_unlock_removes_package(self):
        BehaviorPackageInstance.objects.create(
            definition=self.lock_def,
            obj=self.exit,
            hook="can_traverse",
            data={"attribute": "key_id", "value": "silver"},
        )
        self.caller.search = MagicMock(side_effect=[self.exit, self.key])
        cmd = CmdUnlock()
        cmd.caller = self.caller
        cmd.args = "out with silver key"
        cmd.raw_string = "unlock out with silver key"
        cmd.parse()
        cmd.func()
        self.assertFalse(
            BehaviorPackageInstance.objects.filter(
                definition=self.lock_def, obj=self.exit
            ).exists()
        )

    def test_lock_adds_package(self):
        self.caller.search = MagicMock(side_effect=[self.exit, self.key])
        cmd = CmdLock()
        cmd.caller = self.caller
        cmd.args = "out with silver key"
        cmd.raw_string = "lock out with silver key"
        cmd.parse()
        cmd.func()
        self.assertTrue(
            BehaviorPackageInstance.objects.filter(
                definition=self.lock_def, obj=self.exit
            ).exists()
        )
