"""Covert-org layer integration with the task board (#2820 phase 2)."""

from datetime import timedelta

from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase
from rest_framework.test import APIClient

from world.assets.factories import NPCAssetFactory
from world.assets.services import OrgTransferError, transfer_asset_to_org
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.constants import SPYMASTER_OFFICE
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationTypeFactory,
)
from world.societies.models import OrganizationRank
from world.societies.office_services import appoint_office
from world.tasking.constants import TaskStatus
from world.tasking.exceptions import TaskAssignmentError
from world.tasking.factories import OrgTaskFactory, TaskTemplateFactory
from world.tasking.services import assign_agent
from world.traits.factories import CheckOutcomeFactory


class OrgHeldDispatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.task = OrgTaskFactory(
            template=TaskTemplateFactory(duration=timedelta(days=1)), org=cls.org
        )
        cls.handler = cls.task.issued_by
        OrganizationMembershipFactory(organization=cls.org, persona=cls.handler)
        cls.outcome = CheckOutcomeFactory(name="covert dispatch", success_level=1)

    def test_member_dispatches_org_held_agent(self):
        org_asset = NPCAssetFactory(promoter_persona=None, promoter_org=self.org)
        with force_check_outcome(self.outcome):
            fulfillment = assign_agent(self.task, org_asset, self.handler)
        self.assertEqual(fulfillment.npc_asset, org_asset)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.ASSIGNED)

    def test_other_orgs_agent_rejected(self):
        foreign_org_asset = NPCAssetFactory(
            promoter_persona=None, promoter_org=OrganizationFactory()
        )
        with self.assertRaises(TaskAssignmentError):
            assign_agent(self.task, foreign_org_asset, self.handler)


class TransferAssetToOrgTests(TestCase):
    def test_transfer_flips_holder(self):
        org = OrganizationFactory()
        asset = NPCAssetFactory()
        transfer_asset_to_org(asset, org)
        asset.refresh_from_db()
        self.assertIsNone(asset.promoter_persona)
        self.assertEqual(asset.promoter_org, org)

    def test_transfer_rejects_duplicate_holding(self):
        org = OrganizationFactory()
        asset = NPCAssetFactory()
        transfer_asset_to_org(asset, org)
        sibling_row = NPCAssetFactory(asset_persona=asset.asset_persona)
        with self.assertRaises(OrgTransferError):
            transfer_asset_to_org(sibling_row, org)


class OversightBoardTests(EvenniaTestCase):
    """Parent leadership + spymaster office read child covert boards."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_number=1)
        self.account = self.tenure.player_data.account
        self.persona = self.sheet.primary_persona
        self.parent = OrganizationFactory()
        covert_type = OrganizationTypeFactory(name="wing-type", is_covert=True)
        self.child = OrganizationFactory(org_type=covert_type, parent_org=self.parent)
        self.child_task = OrgTaskFactory(org=self.child)
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _join_parent(self, *, leader: bool):
        rank = (
            OrganizationRank.objects.filter(organization=self.parent, can_manage_ranks=leader)
            .order_by("tier")
            .first()
        )
        OrganizationMembershipFactory(organization=self.parent, persona=self.persona, rank=rank)

    def test_parent_leader_reads_child_board(self):
        self._join_parent(leader=True)
        response = self.client.get("/api/tasking/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["id"] for r in response.data["results"]], [self.child_task.pk])

    def test_spymaster_office_holder_reads_child_board(self):
        self._join_parent(leader=False)
        appoint_office(organization=self.parent, slug=SPYMASTER_OFFICE, holder=self.persona)
        response = self.client.get("/api/tasking/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["id"] for r in response.data["results"]], [self.child_task.pk])

    def test_plain_parent_member_sees_nothing(self):
        self._join_parent(leader=False)
        response = self.client.get("/api/tasking/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_roster_endpoint_scopes_to_oversight(self):
        org_asset = NPCAssetFactory(promoter_persona=None, promoter_org=self.child)
        NPCAssetFactory(promoter_persona=None, promoter_org=OrganizationFactory())
        self._join_parent(leader=True)
        response = self.client.get("/api/tasking/roster/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["id"] for r in response.data["results"]], [org_asset.pk])


class CovertSearchExclusionTests(EvenniaTestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_number=1)
        self.client = APIClient()
        self.client.force_authenticate(user=self.tenure.player_data.account)

    def test_public_org_search_excludes_covert(self):
        overt = OrganizationFactory(name="Gilded Compass Traders")
        covert_type = OrganizationTypeFactory(name="covert-search-type", is_covert=True)
        OrganizationFactory(name="The Unseen Compass", org_type=covert_type)
        response = self.client.get("/api/events/organizations/?name=Compass")
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.data["results"]]
        self.assertEqual(names, [overt.name])
