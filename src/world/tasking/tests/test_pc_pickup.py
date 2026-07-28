"""PC mission pickup tests (#2820 phase 5)."""

from django.test import TestCase

from world.currency.services import get_or_create_purse
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.tasking.constants import TaskStatus
from world.tasking.exceptions import TaskResolutionError
from world.tasking.factories import (
    OrgTaskFactory,
    TaskFulfillmentFactory,
    TaskOutcomeRouteFactory,
    TaskTemplateFactory,
)
from world.tasking.services import (
    accept_task,
    resolve_due_tasks,
    resolve_task_for_mission,
)
from world.traits.factories import CheckOutcomeFactory


class AcceptTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.mission_template = MissionTemplateFactory()
        MissionNodeFactory(template=cls.mission_template, is_entry=True)
        cls.template = TaskTemplateFactory(mission_template=cls.mission_template)
        cls.task = OrgTaskFactory(template=cls.template, org=cls.org)
        cls.handler = cls.task.issued_by
        OrganizationMembershipFactory(organization=cls.org, persona=cls.handler)

    def test_accept_spawns_mission_and_assigns(self):
        fulfillment = accept_task(self.task, self.handler)
        self.assertIsNotNone(fulfillment.mission_instance)
        self.assertIsNone(fulfillment.npc_asset)
        self.assertEqual(fulfillment.mission_instance.template, self.mission_template)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.ASSIGNED)
        self.assertIsNone(self.task.deadline)  # PC path: no offscreen deadline

    def test_accept_requires_mission_template(self):
        npc_only = OrgTaskFactory(template=TaskTemplateFactory(), org=self.org)
        with self.assertRaises(TaskResolutionError):
            accept_task(npc_only, self.handler)


class MissionCompletionSeamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.success = CheckOutcomeFactory(name="pc pickup success", success_level=2)
        cls.failure = CheckOutcomeFactory(name="pc pickup failure", success_level=-1)
        cls.mission_template = MissionTemplateFactory()
        cls.template = TaskTemplateFactory(mission_template=cls.mission_template)

    def _fulfilled_task(self):
        task = OrgTaskFactory(template=self.template, org=self.org)
        task.status = TaskStatus.ASSIGNED
        task.save(update_fields=["status"])
        instance = MissionInstanceFactory(template=self.mission_template)
        fulfillment = TaskFulfillmentFactory(
            task=task,
            npc_asset=None,
            mission_instance=instance,
            handler=task.issued_by,
        )
        return task, instance, fulfillment

    def test_success_terminal_pays_the_task_route(self):
        task, instance, fulfillment = self._fulfilled_task()
        TaskOutcomeRouteFactory(
            template=self.template,
            outcome_tier=self.success,
            money_reward=250,
        )
        terminal_route = MissionOptionRouteFactory(outcome_tier=self.success)
        resolve_task_for_mission(instance, route=terminal_route)

        task.refresh_from_db()
        fulfillment.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(fulfillment.resolved_outcome, self.success)
        handler_sheet = task.issued_by.character_sheet
        self.assertEqual(get_or_create_purse(handler_sheet).balance, 250)

    def test_failure_terminal_fails_the_task(self):
        task, instance, _ = self._fulfilled_task()
        terminal_route = MissionOptionRouteFactory(outcome_tier=self.failure)
        resolve_task_for_mission(instance, route=terminal_route)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_non_task_mission_is_a_noop(self):
        instance = MissionInstanceFactory()
        resolve_task_for_mission(instance, route=None)  # does not raise

    def test_abandoned_mission_fails_task_via_sweep(self):
        task, instance, fulfillment = self._fulfilled_task()
        instance.status = MissionStatus.ABANDONED
        instance.save(update_fields=["status"])
        resolve_due_tasks()
        task.refresh_from_db()
        fulfillment.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIn("unfinished", fulfillment.report)
