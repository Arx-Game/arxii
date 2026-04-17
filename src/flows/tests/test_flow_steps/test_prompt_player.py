"""PROMPT_PLAYER flow step: suspends execution and resumes via Deferred callback."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from flows.consts import FlowActionChoices, FlowState
from flows.execution.prompts import _pending_prompts, resolve_pending_prompt
from flows.factories import (
    FlowDefinitionFactory,
    FlowStackFactory,
    FlowStepDefinitionFactory,
    SceneDataManagerFactory,
)
from flows.flow_execution import FlowExecution


class FlowStateSuspendedTests(TestCase):
    """FlowState.SUSPENDED exists and execute_flow respects it."""

    def test_suspended_state_exists(self) -> None:
        self.assertIn("SUSPENDED", FlowState.__members__)

    def test_execute_flow_exits_on_suspended(self) -> None:
        """execute_flow must not loop past a SUSPENDED execution."""
        flow_def = FlowDefinitionFactory()
        step = FlowStepDefinitionFactory(
            flow=flow_def,
            parent=None,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
        context = SceneDataManagerFactory()
        stack = FlowStackFactory()
        execution = FlowExecution(
            flow_definition=flow_def,
            context=context,
            flow_stack=stack,
            origin=None,
        )
        # Manually suspend before execute_flow is called
        execution.state = FlowState.SUSPENDED
        stack.execute_flow(execution)
        # The loop should have exited immediately — current_step still at step
        self.assertIs(execution.current_step, step)


class PromptPlayerStepTests(TestCase):
    def tearDown(self) -> None:
        _pending_prompts.clear()

    def _build_execution_with_prompt_step(self, account):
        """Build a flow with a PROMPT_PLAYER step and a child sentinel step.

        Uses @owner directly as the account reference (owner IS the account).
        """
        flow_def = FlowDefinitionFactory()
        prompt_step = FlowStepDefinitionFactory(
            flow=flow_def,
            parent=None,
            action=FlowActionChoices.PROMPT_PLAYER,
            variable_name="ask_question",
            parameters={
                "account": "@owner",
                "prompt": "Do you want to proceed?",
                "default_answer": "no",
                "result_variable": "player_answer",
            },
        )
        # Child step: runs after resume; CANCEL_EVENT is a no-op if no dispatch_result.
        # Use parent_id (not parent=) because the factory declares parent_id=None which
        # would otherwise shadow an explicit parent= kwarg.
        FlowStepDefinitionFactory(
            flow=flow_def,
            parent_id=prompt_step.pk,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
        context = SceneDataManagerFactory()
        stack = FlowStackFactory()
        execution = FlowExecution(
            flow_definition=flow_def,
            context=context,
            flow_stack=stack,
            origin=None,
            variable_mapping={"owner": account},
        )
        return execution, stack

    def test_prompt_player_suspends_execution(self) -> None:
        account = AccountFactory()
        execution, stack = self._build_execution_with_prompt_step(account)

        stack.execute_flow(execution)

        self.assertEqual(execution.state, FlowState.SUSPENDED)

    def test_prompt_player_registers_pending_prompt(self) -> None:
        account = AccountFactory()
        execution, stack = self._build_execution_with_prompt_step(account)

        stack.execute_flow(execution)

        account_keys = [k for k in _pending_prompts if k[0] == account.pk]
        self.assertEqual(len(account_keys), 1)

    def test_prompt_player_resumes_on_resolve(self) -> None:
        """resolve_pending_prompt fires Deferred → flow resumes → result_variable set."""
        account = AccountFactory()
        execution, stack = self._build_execution_with_prompt_step(account)

        stack.execute_flow(execution)
        self.assertEqual(execution.state, FlowState.SUSPENDED)

        account_keys = [k for k in _pending_prompts if k[0] == account.pk]
        self.assertEqual(len(account_keys), 1)
        _, prompt_key = account_keys[0]

        resolve_pending_prompt(account_id=account.pk, prompt_key=prompt_key, answer="yes")

        # After resume, execution should no longer be suspended
        self.assertNotEqual(execution.state, FlowState.SUSPENDED)
        # The result variable should hold the answer
        self.assertEqual(execution.variable_mapping.get("player_answer"), "yes")

    def test_prompt_player_current_step_positioned_for_resume(self) -> None:
        """After suspend, current_step points at the child step (resume target)."""
        account = AccountFactory()
        execution, stack = self._build_execution_with_prompt_step(account)

        stack.execute_flow(execution)

        self.assertEqual(execution.state, FlowState.SUSPENDED)
        # current_step is the child (resume-to) step, not None and not the prompt step
        self.assertIsNotNone(execution.current_step)
        self.assertEqual(execution.current_step.action, FlowActionChoices.CANCEL_EVENT)
