from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase

from commands.dispatchers import (
    BaseDispatcher,
    LocationDispatcher,
    TargetDispatcher,
    TargetTextDispatcher,
    TextDispatcher,
)
from commands.exceptions import CommandError
from commands.handlers.base import BaseHandler
from evennia_extensions.factories import ObjectDBFactory


class DummyHandler(BaseHandler):
    def __init__(self):
        super().__init__(flow_name="test_flow")
        self.kwargs = None

    def run(self, **kwargs: Any) -> None:
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
        assert handler.kwargs is not None
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
        assert handler.kwargs is not None
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
        assert handler.kwargs is not None
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
        assert handler.kwargs is not None
        self.assertEqual(handler.kwargs["target"], location)


class FrontendDescriptorTests(TestCase):
    def test_base_descriptor_defaults(self):
        caller = ObjectDBFactory(db_key="caller")
        handler = DummyHandler()
        cmd = DummyCommand(caller, "", cmdname="foo")
        disp = BaseDispatcher(r"^$", handler)
        disp.bind(cmd)
        desc = disp.frontend_descriptor()
        self.assertEqual(desc["action"], "foo")
        self.assertEqual(desc["params_schema"], {})
        self.assertEqual(desc["icon"], "")
        self.assertEqual(desc["prompt"], "dummy")

    def test_target_descriptor_adds_target_param(self):
        caller = ObjectDBFactory(db_key="caller")
        handler = DummyHandler()
        cmd = DummyCommand(caller, "rock")
        disp = TargetDispatcher(r"^(?P<target>.+)$", handler)
        disp.bind(cmd)
        desc = disp.frontend_descriptor()
        self.assertEqual(
            desc["params_schema"],
            {"target": {"type": "string", "match": "searchable_object"}},
        )

    def test_target_text_descriptor_adds_params(self):
        caller = ObjectDBFactory(db_key="caller")
        handler = DummyHandler()
        cmd = DummyCommand(caller, "rock hello")
        disp = TargetTextDispatcher(r"^(?P<target>[^ ]+) (?P<text>.+)$", handler)
        disp.bind(cmd)
        desc = disp.frontend_descriptor()
        self.assertEqual(
            desc["params_schema"],
            {
                "target": {"type": "string", "match": "searchable_object"},
                "text": {"type": "string"},
            },
        )

    def test_target_descriptor_custom_match(self):
        caller = ObjectDBFactory(db_key="caller")
        handler = DummyHandler()
        cmd = DummyCommand(caller, "npc")
        disp = TargetDispatcher(r"^(?P<target>.+)$", handler, target_match="npc")
        disp.bind(cmd)
        desc = disp.frontend_descriptor()
        self.assertEqual(
            desc["params_schema"],
            {"target": {"type": "string", "match": "npc"}},
        )

    def test_text_descriptor_adds_text_param(self):
        caller = ObjectDBFactory(db_key="caller")
        handler = DummyHandler()
        cmd = DummyCommand(caller, "hello")
        disp = TextDispatcher(r"^(?P<text>.+)$", handler)
        disp.bind(cmd)
        desc = disp.frontend_descriptor()
        self.assertEqual(desc["params_schema"], {"text": {"type": "string"}})
