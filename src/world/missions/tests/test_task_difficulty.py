"""A task pickup rolls its AUTHORED CHECKs at the steward-set difficulty (#696 gap 8)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services.resolution import resolve_option
from world.tasking.factories import OrgTaskFactory, TaskFulfillmentFactory
from world.traits.factories import CheckOutcomeFactory

_APPLY = "world.missions.services.resolution.apply_all_effects"


class TaskDifficultyTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.template = MissionTemplateFactory(name="task-tmpl", risk_tier=2)
        self.instance = MissionInstanceFactory(template=self.template)
        self.node = MissionNodeFactory(template=self.template, key="job")
        self.actor = MissionParticipantFactory(
            instance=self.instance, character=self.sheet, is_contract_holder=True
        )
        self.instance.current_node = self.node
        self.instance.save()
        self.success = CheckOutcomeFactory(name="job success", success_level=1)
        self.option = MissionOptionFactory(
            node=self.node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name="JobCheck"),
        )
        MissionOptionRouteFactory(option=self.option, outcome_tier=self.success, target_node=None)

    def _roll(self) -> int | None:
        with force_check_outcome(self.success) as capture, patch(_APPLY):
            resolve_option(self.instance, self.node, self.option, self.actor)
        return capture.target_difficulty

    def test_task_pickup_rolls_at_the_derived_difficulty(self) -> None:
        task = OrgTaskFactory(derived_difficulty=70)
        TaskFulfillmentFactory(task=task, npc_asset=None, mission_instance=self.instance)

        self.assertEqual(self._roll(), 70)

    def test_task_pickup_without_a_derived_difficulty_uses_the_risk_tier(self) -> None:
        task = OrgTaskFactory(derived_difficulty=None)
        TaskFulfillmentFactory(task=task, npc_asset=None, mission_instance=self.instance)

        self.assertEqual(self._roll(), 2)

    def test_ordinary_run_uses_the_risk_tier(self) -> None:
        self.assertEqual(self._roll(), 2)
