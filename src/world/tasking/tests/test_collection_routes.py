"""Collection-landing task routes (#696 item 2)."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from world.checks.test_helpers import force_check_outcome
from world.currency.constants import IncomeStreamKind
from world.currency.models import OrgIncomeStream
from world.currency.services import get_or_create_treasury
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.tasking.factories import (
    OrgTaskFactory,
    TaskOutcomeRouteFactory,
    TaskTemplateFactory,
)
from world.tasking.services import assign_agent, resolve_task
from world.traits.factories import CheckOutcomeFactory


class CollectionRouteTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.assets.factories import NPCAssetFactory

        cls.org = OrganizationFactory()
        cls.win = CheckOutcomeFactory(name="collection route win", success_level=2)
        cls.asset = NPCAssetFactory()
        cls.handler = cls.asset.promoter_persona
        OrganizationMembershipFactory(organization=cls.org, persona=cls.handler)

    def _stream(self, uncollected_pool: int) -> OrgIncomeStream:
        return OrgIncomeStream.objects.create(
            organization=self.org,
            name="Levy pool",
            kind=IncomeStreamKind.DOMAIN_TAX,
            gross_amount=0,
            uncollected_pool=uncollected_pool,
            area=None,
        )

    def _treasury_balance(self) -> int:
        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        return treasury.balance

    def _assign(self, template, **route_kwargs):
        route = TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, **route_kwargs)
        task = OrgTaskFactory(template=template, org=self.org, issued_by=self.handler)
        with force_check_outcome(self.win):
            assign_agent(task, self.asset, self.handler)
        return route, task

    def _resolve(self, template, **route_kwargs):
        route, task = self._assign(template, **route_kwargs)
        with force_check_outcome(self.win):
            fulfillment = resolve_task(task)
        return route, fulfillment


class CollectionRouteTests(CollectionRouteTestBase):
    def test_route_with_collection_level_lands_org_income(self):
        self._stream(1000)
        template = TaskTemplateFactory(duration=timedelta(days=1))
        _route, task = self._assign(template, collection_success_level=3)
        with (
            patch("world.checks.services.perform_check_with_modifiers") as mocked_check,
            force_check_outcome(self.win),
        ):
            fulfillment = resolve_task(task)
        mocked_check.assert_not_called()
        self.assertGreater(self._treasury_balance(), 0)
        self.assertEqual(OrgIncomeStream.objects.get(organization=self.org).uncollected_pool, 0)
        self.assertIn("coppers home", fulfillment.report)

    def test_route_without_level_lands_nothing(self):
        self._stream(1000)
        template = TaskTemplateFactory(duration=timedelta(days=1))
        self._resolve(template, collection_success_level=None)
        self.assertEqual(self._treasury_balance(), 0)
        self.assertEqual(OrgIncomeStream.objects.get(organization=self.org).uncollected_pool, 1000)

    def test_empty_pools_do_not_error(self):
        template = TaskTemplateFactory(duration=timedelta(days=1))
        _route, fulfillment = self._resolve(template, collection_success_level=3)
        self.assertEqual(self._treasury_balance(), 0)
        self.assertIn("held nothing worth collecting", fulfillment.report)
