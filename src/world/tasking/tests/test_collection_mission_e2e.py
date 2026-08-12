"""End-to-end journey for the PLACEHOLDER "Collect the Levies" task/mission (#696).

Steward issues a DOMAIN task off the seeded example content -> a member picks
it up as a mission (``accept_task`` -> ``staff_assign_mission``) -> the
single CHECK option resolves -> the terminal route grades the issuing org's
income collection at its authored ``collection_success_level`` (#696 item 2)
and pays the handler's cut off the SAME route (#696 item 3 worked example).
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from world.areas.factories import AreaFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.constants import IncomeStreamKind
from world.currency.models import OrgIncomeStream
from world.currency.services import get_or_create_purse, get_or_create_treasury
from world.locations.constants import KeyType, LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.missions.models import MissionNode, MissionOption, MissionOptionRoute, MissionTemplate
from world.missions.services.play import resolve_beat_option
from world.scenes.factories import PersonaFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.domain_tasks import (
    MISSION_TEMPLATE_NAME,
    TASK_TEMPLATE_NAME,
    seed_domain_collection_task,
)
from world.seeds.governance_checks import seed_governance_check_content
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import Domain
from world.tasking.constants import TaskStatus
from world.tasking.models import TaskOutcomeRoute, TaskTemplate
from world.tasking.services import accept_task, create_task
from world.traits.models import CheckOutcome


def _write_crime_modifier(area) -> None:
    """Author a CRIME area-level cascade row (mirrors turf_services' pattern)."""
    LocationValueModifier.objects.create(
        parent_type=LocationParentType.AREA,
        area=area,
        room_profile=None,
        key_type=KeyType.STAT,
        stat_key=StatKey.CRIME,
        value=20,
        change_per_day=0,
    )


@override_settings(SEED_SAMPLE_CONTENT=True)  # MissionTemplate et al. are CONTENT_MODELS
class CollectionMissionJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_governance_check_content()
        seed_domain_collection_task()

    def test_steward_task_to_mission_to_landed_collection(self) -> None:
        org = OrganizationFactory()
        area = AreaFactory()
        _write_crime_modifier(area)
        domain = Domain.objects.create(area=area, name="Testmarch", owner_org=org)
        stream = OrgIncomeStream.objects.create(
            organization=org,
            name="Testmarch levies",
            kind=IncomeStreamKind.DOMAIN_TAX,
            gross_amount=0,
            uncollected_pool=1000,
            area=area,
        )
        leader = PersonaFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(organization=org, persona=leader)
        OrganizationMembershipFactory(organization=org, persona=member)

        task_template = TaskTemplate.objects.get(name=TASK_TEMPLATE_NAME)
        task = create_task(task_template, org, leader, target_domain=domain)
        self.assertEqual(task.status, TaskStatus.OPEN)

        fulfillment = accept_task(task, member)
        instance = fulfillment.mission_instance
        self.assertIsNotNone(instance)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.ASSIGNED)

        mission_template = MissionTemplate.objects.get(name=MISSION_TEMPLATE_NAME)
        entry = mission_template.nodes.get(is_entry=True)
        option = entry.options.get()
        success = CheckOutcome.objects.get(name="Success")
        member_character = member.character_sheet.character
        with force_check_outcome(success):
            resolve_beat_option(instance, member_character, option_id=option.pk)

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.COMPLETED)

        treasury = get_or_create_treasury(org)
        treasury.refresh_from_db()
        # Success -> collection_success_level=1 -> COLLECTION_BAND_PCTS floor
        # 1 -> 100% of the gathered 1000, minus the default 10% graft leak.
        self.assertEqual(treasury.balance, 900)

        stream.refresh_from_db()
        self.assertEqual(stream.uncollected_pool, 0)

        purse = get_or_create_purse(member.character_sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 25)

        fulfillment.refresh_from_db()
        self.assertIn("levies", fulfillment.report)
        self.assertIn("PLACEHOLDER", fulfillment.report)

    def test_seed_is_idempotent(self) -> None:
        before = {
            "TaskTemplate": TaskTemplate.objects.count(),
            "TaskOutcomeRoute": TaskOutcomeRoute.objects.count(),
            "MissionTemplate": MissionTemplate.objects.count(),
            "MissionNode": MissionNode.objects.count(),
            "MissionOption": MissionOption.objects.count(),
            "MissionOptionRoute": MissionOptionRoute.objects.count(),
        }

        seed_domain_collection_task()

        after = {
            "TaskTemplate": TaskTemplate.objects.count(),
            "TaskOutcomeRoute": TaskOutcomeRoute.objects.count(),
            "MissionTemplate": MissionTemplate.objects.count(),
            "MissionNode": MissionNode.objects.count(),
            "MissionOption": MissionOption.objects.count(),
            "MissionOptionRoute": MissionOptionRoute.objects.count(),
        }
        self.assertEqual(after, before)
