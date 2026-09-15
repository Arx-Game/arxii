"""The steward's check sets a PC run's difficulty at issue (#696 gap 8)."""

from unittest.mock import patch

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.checks.test_helpers import force_check_outcome
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.services import create_domain
from world.tasking.constants import DIFFICULTY_STEP_PER_LEVEL, TaskTargetKind
from world.tasking.factories import TaskTemplateFactory
from world.tasking.models import OrgTask
from world.tasking.services import assign_agent, create_task, task_difficulty
from world.traits.factories import CheckOutcomeFactory

NORMAL = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]


class IssueDifficultyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.template = TaskTemplateFactory()
        cls.steward = PersonaFactory()
        cls.good = CheckOutcomeFactory(name="issue good", success_level=2)
        cls.botch = CheckOutcomeFactory(name="issue botch", success_level=-20)

    def test_difficulty_is_local_order_shifted_by_the_stewards_check(self) -> None:
        with force_check_outcome(self.good) as capture:
            task = create_task(self.template, self.org, self.steward)

        self.assertEqual(capture.check_type, self.template.check_type)
        self.assertEqual(capture.target_difficulty, NORMAL)  # no target: a quiet area
        self.assertEqual(task.derived_difficulty, NORMAL - 2 * DIFFICULTY_STEP_PER_LEVEL)

    def test_difficulty_clamps_to_the_authored_band_range(self) -> None:
        with force_check_outcome(self.botch):
            task = create_task(self.template, self.org, self.steward)

        self.assertEqual(task.derived_difficulty, DIFFICULTY_VALUES[DifficultyChoice.HARROWING])

    def test_domain_target_reads_the_domains_area(self) -> None:
        area = AreaFactory(name="taxed-march")
        domain = create_domain(area=area, name="Taxed March", owner_org=self.org)
        template = TaskTemplateFactory(target_kind=TaskTargetKind.DOMAIN)

        with (
            patch("world.locations.services.area_order_difficulty", return_value=60) as derive,
            force_check_outcome(self.good),
        ):
            task = create_task(template, self.org, self.steward, target_domain=domain)

        derive.assert_called_once_with(area)
        self.assertEqual(task.derived_difficulty, 60 - 2 * DIFFICULTY_STEP_PER_LEVEL)

    def test_npc_dispatch_rolls_at_the_derived_difficulty(self) -> None:
        from world.assets.factories import NPCAssetFactory
        from world.societies.factories import OrganizationMembershipFactory

        OrganizationMembershipFactory(organization=self.org, persona=self.steward)
        with force_check_outcome(self.good):
            task = create_task(self.template, self.org, self.steward)
        self.assertEqual(task_difficulty(task), task.derived_difficulty)

        asset = NPCAssetFactory(promoter_persona=self.steward)
        with force_check_outcome(self.good) as capture:
            assign_agent(task, asset, self.steward)

        self.assertEqual(capture.target_difficulty, task.derived_difficulty)

    def test_task_difficulty_falls_back_to_the_template(self) -> None:
        task = OrgTask(template=self.template, org=self.org, issued_by=self.steward)
        self.assertEqual(task_difficulty(task), self.template.check_difficulty)

    def test_the_roll_itself_is_not_stored(self) -> None:
        with force_check_outcome(self.good):
            task = create_task(self.template, self.org, self.steward)

        stored = {f.name for f in OrgTask._meta.get_fields()}
        self.assertIn("derived_difficulty", stored)
        self.assertFalse({"issue_check_outcome", "issue_margin"} & stored)
        task.refresh_from_db()
        self.assertEqual(task.derived_difficulty, NORMAL - 2 * DIFFICULTY_STEP_PER_LEVEL)
