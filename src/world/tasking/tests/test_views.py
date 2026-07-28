"""Board API tests (#2820 phase 1)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase
from rest_framework.test import APIClient

from world.assets.factories import NPCAssetFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.models import OrganizationRank
from world.tasking.constants import TaskStatus
from world.tasking.factories import OrgTaskFactory, TaskTemplateFactory


class OrgTaskBoardTestBase(EvenniaTestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_number=1)
        self.account = self.tenure.player_data.account
        self.persona = self.sheet.primary_persona
        self.org = OrganizationFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _join(self, *, leader: bool = False):
        # OrganizationFactory auto-creates the five-tier ladder; pick from it.
        rank = (
            OrganizationRank.objects.filter(organization=self.org, can_manage_ranks=leader)
            .order_by("tier")
            .first()
        )
        return OrganizationMembershipFactory(
            organization=self.org,
            persona=self.persona,
            rank=rank,
        )


class OrgTaskListTests(OrgTaskBoardTestBase):
    def test_non_member_sees_empty_board(self) -> None:
        OrgTaskFactory(org=self.org)
        response = self.client.get("/api/tasking/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_member_sees_org_tasks_without_unresolved_report(self) -> None:
        self._join()
        task = OrgTaskFactory(org=self.org)
        OrgTaskFactory()  # another org — must not appear
        response = self.client.get("/api/tasking/tasks/")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        self.assertEqual([row["id"] for row in rows], [task.pk])
        self.assertIsNone(rows[0]["fulfillment"])


class OrgTaskCreateTests(OrgTaskBoardTestBase):
    def test_non_leader_create_rejected(self) -> None:
        self._join(leader=False)
        template = TaskTemplateFactory()
        response = self.client.post(
            "/api/tasking/tasks/",
            {"template": template.pk, "org": self.org.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_leader_creates_open_task(self) -> None:
        self._join(leader=True)
        template = TaskTemplateFactory()
        response = self.client.post(
            "/api/tasking/tasks/",
            {"template": template.pk, "org": self.org.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], TaskStatus.OPEN)


class OrgTaskAssignTests(OrgTaskBoardTestBase):
    def test_member_assigns_own_agent(self) -> None:
        self._join()
        task = OrgTaskFactory(org=self.org)
        asset = NPCAssetFactory(promoter_persona=self.persona)
        response = self.client.post(
            f"/api/tasking/tasks/{task.pk}/assign/",
            {"npc_asset": asset.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], TaskStatus.ASSIGNED)
        self.assertEqual(response.data["fulfillment"]["agent_name"], str(asset.asset_persona))
        self.assertEqual(response.data["fulfillment"]["report"], "")

    def test_assign_foreign_agent_rejected_with_user_message(self) -> None:
        self._join()
        task = OrgTaskFactory(org=self.org)
        foreign_asset = NPCAssetFactory()
        response = self.client.post(
            f"/api/tasking/tasks/{task.pk}/assign/",
            {"npc_asset": foreign_asset.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "You can only dispatch your own agents.")


class AuthoringPermissionTests(OrgTaskBoardTestBase):
    def test_templates_are_staff_only(self) -> None:
        response = self.client.get("/api/tasking/templates/")
        self.assertEqual(response.status_code, 403)
