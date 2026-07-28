"""Model validation tests for the tasking app (#2820 phase 1)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.societies.factories import OrganizationFactory
from world.tasking.constants import TaskStatus, TaskTargetKind
from world.tasking.factories import (
    OrgTaskFactory,
    TaskFulfillmentFactory,
    TaskOutcomeRouteFactory,
    TaskTemplateFactory,
)


class OrgTaskTargetDiscriminatorTests(TestCase):
    """OrgTask.clean enforces target_kind <-> target FK agreement."""

    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()

    def test_none_kind_with_no_targets_is_valid(self):
        task = OrgTaskFactory(target_kind=TaskTargetKind.NONE)
        task.full_clean()  # does not raise

    def test_none_kind_with_target_fk_raises(self):
        task = OrgTaskFactory.build(
            template=TaskTemplateFactory(),
            org=self.org,
            issued_by=OrgTaskFactory().issued_by,
            target_kind=TaskTargetKind.NONE,
            target_org=self.org,
        )
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_org_kind_with_org_target_is_valid(self):
        task = OrgTaskFactory(target_kind=TaskTargetKind.ORG, target_org=self.org)
        task.full_clean()  # does not raise

    def test_org_kind_missing_org_target_raises(self):
        task = OrgTaskFactory.build(
            template=TaskTemplateFactory(),
            org=self.org,
            issued_by=OrgTaskFactory().issued_by,
            target_kind=TaskTargetKind.ORG,
        )
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_org_kind_with_wrong_fk_populated_raises(self):
        other = OrgTaskFactory()
        task = OrgTaskFactory.build(
            template=TaskTemplateFactory(),
            org=self.org,
            issued_by=other.issued_by,
            target_kind=TaskTargetKind.ORG,
            target_org=self.org,
            target_persona=other.issued_by,
        )
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_default_status_is_open(self):
        task = OrgTaskFactory()
        self.assertEqual(task.status, TaskStatus.OPEN)


class TaskFulfillmentSourceTests(TestCase):
    """Exactly one of npc_asset / mission_instance is set."""

    def test_npc_asset_only_is_valid(self):
        fulfillment = TaskFulfillmentFactory()
        fulfillment.full_clean()  # does not raise

    def test_neither_source_raises(self):
        fulfillment = TaskFulfillmentFactory.build(
            task=OrgTaskFactory(),
            npc_asset=None,
            handler=OrgTaskFactory().issued_by,
        )
        with self.assertRaises(ValidationError):
            fulfillment.full_clean()

    def test_only_one_active_fulfillment_per_task(self):
        fulfillment = TaskFulfillmentFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TaskFulfillmentFactory(task=fulfillment.task)
        # A retired fulfillment does not block a new active one.
        fulfillment.is_active = False
        fulfillment.save()
        TaskFulfillmentFactory(task=fulfillment.task)  # does not raise


class TaskOutcomeRouteTests(TestCase):
    def test_duplicate_tier_per_template_raises(self):
        route = TaskOutcomeRouteFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TaskOutcomeRouteFactory(template=route.template, outcome_tier=route.outcome_tier)
