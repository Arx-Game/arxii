"""Declarative AP/fatigue cost on the Action base (#1154)."""

from dataclasses import dataclass
from typing import Any

from django.test import TestCase

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionContext, ActionResult, TargetType
from evennia_extensions.factories import ObjectDBFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.services import get_or_create_fatigue_pool


@dataclass
class _ApAction(Action):
    key: str = "test_ap_cost"
    name: str = "AP Cost"
    icon: str = "x"
    category: str = "test"
    target_type: TargetType = TargetType.SELF
    ap_cost: int = 3

    def execute(
        self, actor: Any, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        return ActionResult(success=True, message="executed")


@dataclass
class _FatigueAction(Action):
    key: str = "test_fatigue_cost"
    name: str = "Fatigue Cost"
    icon: str = "x"
    category: str = "test"
    target_type: TargetType = TargetType.SELF
    fatigue_cost: int = 4
    fatigue_category: str = ActionCategory.MENTAL

    def execute(
        self, actor: Any, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        return ActionResult(success=True, message="executed")


class ActionApCostTests(TestCase):
    def setUp(self) -> None:
        self.actor = ObjectDBFactory(db_key="Searcher")
        self.pool = ActionPointPool.get_or_create_for_character(self.actor)

    def test_ap_is_charged_before_execute(self) -> None:
        self.pool.current = 10
        self.pool.save()

        result = _ApAction().run(self.actor)

        assert result.message == "executed"
        self.pool.refresh_from_db()
        assert self.pool.current == 7

    def test_insufficient_ap_blocks_execution(self) -> None:
        self.pool.current = 1
        self.pool.save()

        result = _ApAction().run(self.actor)

        assert result.success is False
        assert "action point" in result.message.lower()
        self.pool.refresh_from_db()
        assert self.pool.current == 1  # not spent; execute never ran


class ActionFatigueCostTests(TestCase):
    def test_fatigue_is_applied_on_run(self) -> None:
        sheet = CharacterSheetFactory()
        actor = sheet.character
        before = get_or_create_fatigue_pool(sheet).get_current(ActionCategory.MENTAL)

        result = _FatigueAction().run(actor)

        assert result.message == "executed"
        after = get_or_create_fatigue_pool(sheet).get_current(ActionCategory.MENTAL)
        assert after > before
