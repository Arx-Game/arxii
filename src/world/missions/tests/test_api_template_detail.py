"""Phase D D1.3: MissionTemplateViewSet detail (§5 footprint).

The detail endpoint returns the template's full authoring footprint:
- list fields (round-trip of every MissionTemplate column)
- ``lifetime_completions`` — count of COMPLETE MissionInstance rows
- ``active_instances`` — list of currently-ACTIVE MissionInstance rows,
  each with its current node key (or None) and contract-holder name.

Reads only — staff browse never mutates run state. CRUD on instances
is staff-power (D4); CRUD on the template's own fields is D1.2's
ModelViewSet write paths.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)


class TemplateDetailFootprintTests(TestCase):
    """Detail response carries §5 footprint metrics."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-detail-ft", is_staff=True)
        cls.template = MissionTemplateFactory(name="The Heist", slug="the-heist")
        cls.entry_node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)

        # Two complete runs.
        for _ in range(2):
            MissionInstanceFactory(template=cls.template, status=MissionStatus.COMPLETE)
        # One abandoned run (not a completion, not active).
        MissionInstanceFactory(template=cls.template, status=MissionStatus.ABANDONED)
        # Three live runs at the entry node.
        cls.live_holder = CharacterFactory(db_key="LiveHolder")
        cls.live_instance = MissionInstanceFactory(
            template=cls.template,
            status=MissionStatus.ACTIVE,
            current_node=cls.entry_node,
        )
        MissionParticipantFactory(
            instance=cls.live_instance,
            character=cls.live_holder,
            is_contract_holder=True,
        )
        for _ in range(2):
            MissionInstanceFactory(
                template=cls.template,
                status=MissionStatus.ACTIVE,
                current_node=cls.entry_node,
            )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _detail(self) -> dict:
        response = self.client.get(f"/api/missions/templates/{self.template.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_includes_list_fields(self) -> None:
        data = self._detail()
        self.assertEqual(data["slug"], "the-heist")
        self.assertEqual(data["name"], "The Heist")

    def test_includes_lifetime_completions(self) -> None:
        data = self._detail()
        # 2 COMPLETE, ignoring ABANDONED and ACTIVE.
        self.assertEqual(data["lifetime_completions"], 2)

    def test_includes_active_instances_count_and_shape(self) -> None:
        data = self._detail()
        active = data["active_instances"]
        self.assertEqual(len(active), 3)
        # Each row carries instance_id + current_node_key + contract_holder.
        for row in active:
            self.assertIn("instance_id", row)
            self.assertIn("current_node_key", row)
            self.assertIn("contract_holder", row)

    def test_active_includes_current_node_key(self) -> None:
        data = self._detail()
        keys = {row["current_node_key"] for row in data["active_instances"]}
        # All three live runs are at the entry node.
        self.assertEqual(keys, {"entry"})

    def test_active_includes_contract_holder_name(self) -> None:
        data = self._detail()
        holders = {row["contract_holder"] for row in data["active_instances"]}
        # One has a named holder; the others have None (no participants added).
        self.assertIn("LiveHolder", holders)
        self.assertIn(None, holders)

    def test_excludes_complete_and_abandoned_from_active(self) -> None:
        data = self._detail()
        # Only ACTIVE runs in the active_instances list.
        for row in data["active_instances"]:
            # No status field exposed on each row — assert by count alone:
            # we set up 3 ACTIVE rows; if COMPLETE/ABANDONED leaked, count
            # would be > 3.
            self.assertIn("instance_id", row)
        self.assertEqual(len(data["active_instances"]), 3)

    def test_template_with_no_runs(self) -> None:
        empty = MissionTemplateFactory(name="No Runs", slug="no-runs")
        response = self.client.get(f"/api/missions/templates/{empty.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["lifetime_completions"], 0)
        self.assertEqual(response.data["active_instances"], [])
