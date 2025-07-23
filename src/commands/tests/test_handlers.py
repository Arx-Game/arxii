from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.command import ArxCommand
from commands.dispatchers import BaseDispatcher
from commands.exceptions import CommandError
from commands.handlers.base import BaseHandler
from evennia_extensions.factories import ObjectDBFactory
from flows.consts import FlowState
from flows.factories import FlowDefinitionFactory
from flows.flow_stack import FlowStack
from flows.models import FlowDefinition


class BaseHandlerTests(TestCase):
    def test_run_primes_context_and_executes_flow(self):
        caller = ObjectDBFactory(db_key="caller")
        target = ObjectDBFactory(db_key="target")
        flow_def = FlowDefinitionFactory(name="main")
        handler = BaseHandler(flow_name=flow_def.name)
        with patch.object(FlowDefinition.objects, "get", return_value=flow_def):
            with patch.object(
                FlowStack,
                "create_and_execute_flow",
                return_value=MagicMock(state=FlowState.RUNNING),
            ) as mock_exec:
                handler.run(caller=caller, target=target)
                self.assertIn(caller.pk, handler.context.states)
                self.assertIn(target.pk, handler.context.states)
                mock_exec.assert_called_once()

    def test_prerequisite_stop_raises_error(self):
        caller = ObjectDBFactory(db_key="caller")
        flow_def = FlowDefinitionFactory(name="main")
        handler = BaseHandler(flow_name=flow_def.name, prerequisite_events=["pre"])
        with (
            patch.object(FlowDefinition.objects, "get", return_value=flow_def),
            patch.object(
                FlowDefinition,
                "emit_event_definition",
                return_value=MagicMock(steps=MagicMock(all=lambda: [])),
            ),
            patch.object(
                FlowStack,
                "create_and_execute_flow",
                return_value=MagicMock(state=FlowState.STOP, stop_reason="blocked"),
            ),
        ):
            with self.assertRaises(CommandError):
                handler.run(caller=caller)


class CommandErrorMessageTests(TestCase):
    def test_caller_receives_error_message(self):
        class FailingHandler:
            def run(self, **kwargs):
                raise CommandError("bad")

        dispatcher = BaseDispatcher(r"^$", FailingHandler())

        class TestCmd(ArxCommand):
            key = "fail"
            dispatchers = [dispatcher]

        caller = ObjectDBFactory(db_key="caller")
        caller.msg = MagicMock()

        cmd = TestCmd()
        cmd.caller = caller
        cmd.args = ""
        cmd.raw_string = ""
        dispatcher.bind(cmd)
        cmd.selected_dispatcher = dispatcher

        cmd.func()

        caller.msg.assert_called_once()
        sent = caller.msg.call_args.kwargs["text"]
        self.assertEqual(str(sent), "bad")
