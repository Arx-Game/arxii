from unittest.mock import MagicMock

from django.test import TestCase

from commands.dispatchers import BaseDispatcher, LocationDispatcher, TargetDispatcher
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory


class DummyHandler:
    def __init__(self):
        self.kwargs = None

    def run(self, **kwargs):
        self.kwargs = kwargs


class DummyCommand:
    def __init__(self, caller, args, raw_string=None, key="dummy", cmdname=None):
        self.caller = caller
        self.args = args
        self.raw_string = raw_string or args
        self.key = key
        self.cmdname = cmdname or key


class BaseDispatcherTests(TestCase):
    def test_execute_passes_kwargs_to_handler(self):
        caller = ObjectDBFactory(db_key="caller")
        handler = DummyHandler()
        cmd = DummyCommand(caller, "", cmdname="look")
        disp = BaseDispatcher(r"^$", handler, command_var="alias")
        disp.bind(cmd)
        self.assertTrue(disp.is_match())
        disp.execute()
        self.assertEqual(handler.kwargs["caller"], caller)
        self.assertEqual(handler.kwargs["alias"], "look")


class TargetDispatcherTests(TestCase):
    def test_target_resolved_and_passed(self):
        caller = ObjectDBFactory(db_key="caller")
        target = ObjectDBFactory(db_key="target")
        caller.search = MagicMock(return_value=target)
        handler = DummyHandler()
        cmd = DummyCommand(caller, "target")
        disp = TargetDispatcher(r"^(?P<target>.+)$", handler)
        disp.bind(cmd)
        disp.execute()
        self.assertEqual(handler.kwargs["target"], target)

    def test_missing_target_raises(self):
        caller = ObjectDBFactory(db_key="caller")
        caller.search = MagicMock(return_value=None)
        handler = DummyHandler()
        cmd = DummyCommand(caller, "nobody")
        disp = TargetDispatcher(r"^(?P<target>.+)$", handler)
        disp.bind(cmd)
        with self.assertRaises(CommandError):
            disp.execute()

    def test_command_var_passed(self):
        caller = ObjectDBFactory(db_key="caller")
        target = ObjectDBFactory(db_key="rock")
        caller.search = MagicMock(return_value=target)
        handler = DummyHandler()
        cmd = DummyCommand(caller, "rock", cmdname="glance")
        disp = TargetDispatcher(r"^(?P<target>.+)$", handler, command_var="alias")
        disp.bind(cmd)
        disp.execute()
        self.assertEqual(handler.kwargs["alias"], "glance")


class LocationDispatcherTests(TestCase):
    def test_location_passed(self):
        location = ObjectDBFactory(db_key="room")
        caller = ObjectDBFactory(db_key="caller", location=location)
        handler = DummyHandler()
        cmd = DummyCommand(caller, "look")
        disp = LocationDispatcher(r"^look$", handler)
        disp.bind(cmd)
        disp.execute()
        self.assertEqual(handler.kwargs["target"], location)
