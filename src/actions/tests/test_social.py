"""Tests for social action stubs."""

from django.test import TestCase

from actions.definitions.social import (
    DeceiveAction,
    EntranceAction,
    FlirtAction,
    IntimidateAction,
    PerformAction,
    PersuadeAction,
)
from actions.registry import get_action
from actions.types import TargetType
from evennia_extensions.factories import ObjectDBFactory


class SocialActionStubTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor = ObjectDBFactory(db_key="Alice")
        cls.target = ObjectDBFactory(db_key="Bob")

    def test_intimidate_registered(self) -> None:
        action = get_action("intimidate")
        assert action is not None
        assert action.category == "social"
        assert action.target_type == TargetType.SINGLE

    def test_persuade_registered(self) -> None:
        action = get_action("persuade")
        assert action is not None
        assert action.category == "social"

    def test_deceive_registered(self) -> None:
        action = get_action("deceive")
        assert action is not None

    def test_flirt_registered(self) -> None:
        action = get_action("flirt")
        assert action is not None

    def test_perform_registered(self) -> None:
        action = get_action("perform")
        assert action is not None
        assert action.target_type == TargetType.AREA

    def test_entrance_registered(self) -> None:
        action = get_action("entrance")
        assert action is not None
        assert action.target_type == TargetType.AREA

    def test_intimidate_execute(self) -> None:
        action = IntimidateAction()
        result = action.run(self.actor, target=self.target)
        assert result.success is True

    def test_persuade_execute(self) -> None:
        action = PersuadeAction()
        result = action.run(self.actor, target=self.target)
        assert result.success is True

    def test_deceive_execute(self) -> None:
        action = DeceiveAction()
        result = action.run(self.actor, target=self.target)
        assert result.success is True

    def test_flirt_execute(self) -> None:
        action = FlirtAction()
        result = action.run(self.actor, target=self.target)
        assert result.success is True

    def test_perform_execute(self) -> None:
        action = PerformAction()
        result = action.run(self.actor)
        assert result.success is True

    def test_entrance_execute(self) -> None:
        action = EntranceAction()
        result = action.run(self.actor)
        assert result.success is True
