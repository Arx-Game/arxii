"""Tests for the base Action class and types."""

from dataclasses import dataclass

from django.test import TestCase

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.registry import ACTIONS_BY_KEY, get_action, get_actions_for_target_type
from actions.types import ActionResult, TargetType
from evennia_extensions.factories import ObjectDBFactory


@dataclass
class AlwaysFailsPrerequisite(Prerequisite):
    reason: str = "Not available"

    def is_met(
        self,
        actor: object,  # noqa: ARG002
        target: object = None,  # noqa: ARG002
        context: object = None,  # noqa: ARG002
    ) -> tuple[bool, str]:
        return False, self.reason


@dataclass
class AlwaysPassesPrerequisite(Prerequisite):
    def is_met(
        self,
        actor: object,  # noqa: ARG002
        target: object = None,  # noqa: ARG002
        context: object = None,  # noqa: ARG002
    ) -> tuple[bool, str]:
        return True, ""


@dataclass
class SimpleTestAction(Action):
    key: str = "test"
    name: str = "Test"
    icon: str = "test"
    category: str = "test"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: object, **kwargs: object) -> ActionResult:  # noqa: ARG002
        return ActionResult(success=True, message="done")


@dataclass
class GatedTestAction(Action):
    key: str = "gated"
    name: str = "Gated"
    icon: str = "lock"
    category: str = "test"
    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [AlwaysFailsPrerequisite(reason="You need the key")]

    def execute(self, actor: object, **kwargs: object) -> ActionResult:  # noqa: ARG002
        return ActionResult(success=True, message="unlocked")


class ActionBaseTests(TestCase):
    def test_action_run_calls_execute(self):
        action = SimpleTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        result = action.run(actor)
        assert result.success is True
        assert result.message == "done"

    def test_check_availability_passes_when_no_prerequisites(self):
        action = SimpleTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        avail = action.check_availability(actor)
        assert avail.available is True
        assert avail.reasons == []

    def test_check_availability_fails_with_reason(self):
        action = GatedTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        target = ObjectDBFactory(db_key="Door")
        avail = action.check_availability(actor, target=target)
        assert avail.available is False
        assert "You need the key" in avail.reasons

    def test_check_availability_with_multiple_prerequisites(self):
        @dataclass
        class MultiGatedAction(Action):
            key: str = "multi"
            name: str = "Multi"
            icon: str = "lock"
            category: str = "test"
            target_type: TargetType = TargetType.SELF

            def get_prerequisites(self) -> list[Prerequisite]:
                return [
                    AlwaysFailsPrerequisite(reason="Missing A"),
                    AlwaysPassesPrerequisite(),
                    AlwaysFailsPrerequisite(reason="Missing B"),
                ]

            def execute(self, actor: object, **kwargs: object) -> ActionResult:  # noqa: ARG002
                return ActionResult(success=True)

        action = MultiGatedAction()
        actor = ObjectDBFactory(db_key="Alice")
        avail = action.check_availability(actor)
        assert avail.available is False
        assert len(avail.reasons) == 2
        assert "Missing A" in avail.reasons
        assert "Missing B" in avail.reasons


class ActionRegistryTests(TestCase):
    def test_get_action_by_key(self):
        action = get_action("look")
        assert action is not None
        assert action.key == "look"

    def test_get_action_returns_none_for_unknown(self):
        assert get_action("nonexistent") is None

    def test_all_expected_actions_registered(self):
        expected_keys = {
            "look",
            "inventory",
            "say",
            "pose",
            "whisper",
            "get",
            "drop",
            "give",
            "traverse_exit",
            "home",
        }
        assert set(ACTIONS_BY_KEY.keys()) == expected_keys

    def test_get_actions_for_target_type(self):
        self_actions = get_actions_for_target_type(TargetType.SELF)
        self_keys = {a.key for a in self_actions}
        assert "inventory" in self_keys
        assert "home" in self_keys

    def test_single_target_actions(self):
        single_actions = get_actions_for_target_type(TargetType.SINGLE)
        single_keys = {a.key for a in single_actions}
        assert "look" in single_keys
        assert "get" in single_keys
        assert "whisper" in single_keys
