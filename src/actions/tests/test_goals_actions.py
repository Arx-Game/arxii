"""Unit tests for the goal Actions (#1350)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.goals import LogGoalProgressAction, SetCharacterGoalsAction
from actions.registry import get_action
from actions.types import ActionResult
from world.character_sheets.factories import CharacterSheetFactory
from world.goals.factories import GoalDomainFactory
from world.goals.models import CharacterGoal, GoalJournal


class SetCharacterGoalsActionTests(TestCase):
    def setUp(self) -> None:
        self.actor = CharacterSheetFactory().character
        self.domain = GoalDomainFactory()

    def test_registry_key_present(self) -> None:
        assert get_action("set_character_goals") == SetCharacterGoalsAction()

    def test_sets_goals(self) -> None:
        result: ActionResult = SetCharacterGoalsAction().execute(
            actor=self.actor,
            goals=[{"domain": self.domain.pk, "points": 10, "notes": "x"}],
        )
        assert result.success
        assert CharacterGoal.objects.filter(character=self.actor.sheet_data, points=10).exists()

    def test_over_cap_fails(self) -> None:
        result = SetCharacterGoalsAction().execute(
            actor=self.actor,
            goals=[{"domain": self.domain.pk, "points": 999, "notes": ""}],
        )
        assert not result.success
        assert "exceed" in (result.message or "").lower()


class LogGoalProgressActionTests(TestCase):
    def setUp(self) -> None:
        self.actor = CharacterSheetFactory().character

    def test_logs_progress(self) -> None:
        result = LogGoalProgressAction().execute(
            actor=self.actor, title="A step", content="Did a thing", is_public=False
        )
        assert result.success
        journal = GoalJournal.objects.get(character=self.actor.sheet_data, title="A step")
        assert journal.xp_awarded == 1
