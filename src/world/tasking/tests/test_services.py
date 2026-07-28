"""Service tests for tasking assign/resolve (#2820 phase 1).

Checks are forced via world.checks.test_helpers.force_check_outcome — the
official seam — so no real trait data is needed.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.assets.constants import AssetStatus
from world.assets.factories import CluePoolEntryFactory, CluePoolFactory, NPCAssetFactory
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.models import CharacterClue
from world.currency.services import get_or_create_purse
from world.roster.factories import RosterEntryFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.tasking.constants import DISPATCH_MARGIN_STEP, TaskStatus
from world.tasking.exceptions import TaskAssignmentError, TaskResolutionError
from world.tasking.factories import OrgTaskFactory, TaskOutcomeRouteFactory, TaskTemplateFactory
from world.tasking.services import assign_agent, resolve_due_tasks, resolve_task
from world.traits.factories import CheckOutcomeFactory


class TaskingServiceTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.template = TaskTemplateFactory(duration=timedelta(days=1))
        cls.task = OrgTaskFactory(template=cls.template, org=cls.org)
        cls.handler = cls.task.issued_by
        OrganizationMembershipFactory(organization=cls.org, persona=cls.handler)
        cls.asset = NPCAssetFactory(promoter_persona=cls.handler)
        cls.success = CheckOutcomeFactory(name="task success", success_level=2)
        cls.failure = CheckOutcomeFactory(name="task failure", success_level=-1)


class AssignAgentTests(TaskingServiceTestBase):
    def test_assign_rolls_dispatch_and_sets_deadline(self):
        with force_check_outcome(self.success):
            fulfillment = assign_agent(self.task, self.asset, self.handler)

        self.assertEqual(fulfillment.handler_check_outcome, self.success)
        self.assertEqual(fulfillment.handler_margin, 2 * DISPATCH_MARGIN_STEP)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.ASSIGNED)
        self.assertIsNotNone(self.task.deadline)
        self.assertGreater(self.task.deadline, timezone.now())

    def test_assign_rejects_foreign_asset(self):
        other_asset = NPCAssetFactory()
        with self.assertRaises(TaskAssignmentError):
            assign_agent(self.task, other_asset, self.handler)

    def test_assign_rejects_non_member_handler(self):
        outsider_asset = NPCAssetFactory()
        outsider = outsider_asset.promoter_persona
        with self.assertRaises(TaskAssignmentError):
            assign_agent(self.task, outsider_asset, outsider)

    def test_assign_rejects_inactive_asset(self):
        self.asset.status = AssetStatus.COMPROMISED
        self.asset.save()
        with self.assertRaises(TaskAssignmentError):
            assign_agent(self.task, self.asset, self.handler)

    def test_assign_rejects_non_open_task(self):
        with force_check_outcome(self.success):
            assign_agent(self.task, self.asset, self.handler)
        with self.assertRaises(TaskAssignmentError):
            assign_agent(self.task, self.asset, self.handler)


class ResolveTaskTests(TaskingServiceTestBase):
    def _assign(self, dispatch_outcome=None):
        with force_check_outcome(dispatch_outcome or self.success):
            return assign_agent(self.task, self.asset, self.handler)

    def test_success_pays_money_and_clue_and_completes(self):
        roster_entry = RosterEntryFactory(character_sheet=self.handler.character_sheet)
        clue_pool = CluePoolFactory()
        entry = CluePoolEntryFactory(pool=clue_pool)
        TaskOutcomeRouteFactory(
            template=self.template,
            outcome_tier=self.success,
            money_reward=100,
            clue_pool=clue_pool,
            report_template="{agent} pulled off {task} against {target}.",
        )
        fulfillment = self._assign()
        with force_check_outcome(self.success):
            fulfillment = resolve_task(self.task)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.COMPLETED)
        self.assertEqual(fulfillment.resolved_outcome, self.success)
        self.assertIn("pulled off", fulfillment.report)
        self.assertEqual(get_or_create_purse(self.handler.character_sheet).balance, 100)
        self.assertTrue(
            CharacterClue.objects.filter(roster_entry=roster_entry, clue=entry.clue).exists()
        )

    def test_failure_with_no_route_pays_nothing_and_fails(self):
        self._assign()
        with force_check_outcome(self.failure):
            fulfillment = resolve_task(self.task)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.FAILED)
        self.assertEqual(get_or_create_purse(self.handler.character_sheet).balance, 0)
        self.assertEqual(fulfillment.resolved_outcome, self.failure)
        # No route: generic report line still tells the handler something.
        self.assertNotEqual(fulfillment.report, "")

    def test_botch_pool_compromises_only_dispatched_asset(self):
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=self.failure)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type="asset_status",
            asset_status_target=AssetStatus.COMPROMISED,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        self.template.consequence_pool = pool
        self.template.save()
        bystander_asset = NPCAssetFactory(promoter_persona=self.handler)

        self._assign()
        with force_check_outcome(self.failure):
            resolve_task(self.task)

        self.asset.refresh_from_db()
        bystander_asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.COMPROMISED)
        self.assertEqual(bystander_asset.status, AssetStatus.ACTIVE)

    def test_success_with_pool_leaves_asset_active(self):
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=self.failure)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type="asset_status",
            asset_status_target=AssetStatus.COMPROMISED,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        self.template.consequence_pool = pool
        self.template.save()

        self._assign()
        with force_check_outcome(self.success):
            resolve_task(self.task)

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ACTIVE)

    def test_resolve_requires_assigned_status(self):
        with self.assertRaises(TaskResolutionError):
            resolve_task(self.task)

    def test_second_resolve_is_rejected(self):
        self._assign()
        with force_check_outcome(self.success):
            resolve_task(self.task)
        with self.assertRaises(TaskResolutionError):
            resolve_task(self.task)


class ResolveDueTasksTests(TaskingServiceTestBase):
    def test_cron_resolves_only_past_deadline(self):
        with force_check_outcome(self.success):
            assign_agent(self.task, self.asset, self.handler)

        # Future deadline: nothing due.
        self.assertEqual(resolve_due_tasks(), 0)

        self.task.deadline = timezone.now() - timedelta(minutes=1)
        self.task.save(update_fields=["deadline"])
        with force_check_outcome(self.success):
            count = resolve_due_tasks()
        self.assertEqual(count, 1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.COMPLETED)

    def test_cron_registered(self):
        from world.game_clock.task_registry import get_registered_tasks
        from world.game_clock.tasks import register_all_tasks

        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("tasking.resolve_due_tasks", keys)
