"""Integration tests for the #2820 tasking actions (the telnet/web shared seam)."""

from datetime import timedelta

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import RoomProfileFactory
from world.assets.factories import NPCAssetFactory
from world.checks.test_helpers import force_check_outcome
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.models import OrganizationRank
from world.tasking.constants import TaskStatus
from world.tasking.factories import OrgTaskFactory, TaskTemplateFactory
from world.tasking.models import ListenerPost, OrgTask
from world.traits.factories import CheckOutcomeFactory


class TaskingActionTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.template = TaskTemplateFactory(duration=timedelta(days=1))
        cls.win = CheckOutcomeFactory(name="action seam win", success_level=2)

    def _member(self, *, leader: bool = False):
        """A character whose ACTIVE (primary) persona is an org member (or leader).

        Actions act as the actor's active persona, so the membership and the
        agent must hang on the sheet's primary persona — not a sibling one.
        """
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        asset = NPCAssetFactory(promoter_persona=persona)
        rank = (
            OrganizationRank.objects.filter(organization=self.org, can_manage_ranks=leader)
            .order_by("tier")
            .first()
        )
        OrganizationMembershipFactory(organization=self.org, persona=persona, rank=rank)
        return sheet.character, persona, asset


class IssueAndDispatchActionTests(TaskingActionTestBase):
    def test_leader_issues_task_via_action(self):
        character, _, _ = self._member(leader=True)
        result = get_action("issue_org_task").run(
            character, template_id=self.template.pk, org_id=self.org.pk
        )
        self.assertTrue(result.success)
        task = OrgTask.objects.get(pk=result.data["task_id"])
        self.assertEqual(task.status, TaskStatus.OPEN)

    def test_non_leader_cannot_issue(self):
        character, _, _ = self._member(leader=False)
        result = get_action("issue_org_task").run(
            character, template_id=self.template.pk, org_id=self.org.pk
        )
        self.assertFalse(result.success)
        self.assertIn("leadership", result.message)

    def test_member_assigns_own_agent_via_action(self):
        character, persona, asset = self._member()
        task = OrgTaskFactory(template=self.template, org=self.org, issued_by=persona)
        with force_check_outcome(self.win):
            result = get_action("assign_task_agent").run(
                character, task_id=task.pk, npc_asset_id=asset.pk
            )
        self.assertTrue(result.success)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.ASSIGNED)

    def test_board_lists_org_tasks(self):
        character, persona, _ = self._member()
        task = OrgTaskFactory(template=self.template, org=self.org, issued_by=persona)
        result = get_action("list_org_tasks").run(character)
        self.assertTrue(result.success)
        self.assertIn(f"#{task.pk}", result.message)


class ListenerActionTests(TaskingActionTestBase):
    def _posted(self):
        character, persona, asset = self._member()
        room = RoomProfileFactory()
        character.db_location = room.objectdb
        character.save()
        result = get_action("post_listener").run(character, npc_asset_id=asset.pk)
        return character, persona, room, result

    def test_post_and_collect_where_you_stand(self):
        character, _, room, post_result = self._posted()
        self.assertTrue(post_result.success)
        post = ListenerPost.objects.get(pk=post_result.data["post_id"])
        self.assertEqual(post.assignment.room_id, room.pk)
        # Nothing banked yet: collect fails with the service's message.
        collect = get_action("collect_harvest").run(character)
        self.assertFalse(collect.success)

    def test_detect_reveals_the_listener(self):
        from world.checks.factories import CheckTypeFactory

        CheckTypeFactory(name="Perception")
        from world.character_sheets.factories import CharacterSheetFactory

        character, _, _, _ = self._posted()
        # A different character sweeps the same room.
        rival = CharacterSheetFactory().character
        rival.db_location = character.db_location
        rival.save()
        with force_check_outcome(self.win):
            result = get_action("detect_listeners").run(rival)
        self.assertTrue(result.success)
        self.assertIn("listening", result.message)
