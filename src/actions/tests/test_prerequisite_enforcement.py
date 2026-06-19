"""Tests that Action.run() enforces prerequisites before executing."""

from dataclasses import dataclass

from django.test import TestCase

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType
from evennia_extensions.factories import ObjectDBFactory


@dataclass
class _DenyPrereq(Prerequisite):
    def is_met(self, actor, target=None, context=None):
        return False, "Nope."


@dataclass
class _RunRecorder(Action):
    key: str = "test_recorder"
    name: str = "Recorder"
    icon: str = "x"
    category: str = "test"
    target_type: TargetType = TargetType.SELF
    executed: bool = False

    def get_prerequisites(self):
        return [_DenyPrereq()]

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        object.__setattr__(self, "executed", True)
        return ActionResult(success=True)


class PrerequisiteEnforcementTests(TestCase):
    def test_run_blocks_on_unmet_prerequisite(self) -> None:
        actor = ObjectDBFactory(db_key="EnforceAlice")
        action = _RunRecorder()
        result = action.run(actor)
        assert result.success is False
        assert "Nope." in (result.message or "")
        assert action.executed is False
