"""Tests for the BUILDING_UPGRADE project kind (#1888).

Owner-gated ``start_building_upgrade`` tests use ``RoomBuilderBase`` (which
sets up an owned building) and are tagged ``postgres`` because the owner-gate
walks the ``AreaClosure`` materialized view. Completion-handler tests bypass
``is_owner`` (they build details directly via the factory) and so run on the
SQLite fast tier too.
"""

from django.test import TestCase, tag

from world.buildings.factories import (
    BuildingFactory,
    BuildingUpgradeDetailsFactory,
)
from world.buildings.room_constants import (
    MAX_BUILDING_SIZE_TIER,
    UPGRADE_THRESHOLD_PER_TIER,
)
from world.buildings.room_services import RoomBuildError
from world.buildings.seeds import ensure_building_size_tiers
from world.buildings.tests.test_room_services import RoomBuilderBase
from world.buildings.upgrade_services import (
    BuildingUpgradeError,
    complete_building_upgrade,
    start_building_upgrade,
)
from world.projects.constants import CompletionMode, ProjectKind
from world.projects.factories import ProjectFactory


@tag("postgres")  # start_building_upgrade's is_owner gate walks AreaClosure
class StartBuildingUpgradeTests(RoomBuilderBase):
    def setUp(self) -> None:
        ensure_building_size_tiers()

    def test_commission_creates_project_and_details(self) -> None:
        project = start_building_upgrade(
            persona=self.owner, building=self.building, new_target_size=6
        )
        self.assertEqual(project.kind, ProjectKind.BUILDING_UPGRADE)
        self.assertEqual(project.completion_mode, CompletionMode.SINGLE_THRESHOLD)
        self.assertEqual(project.threshold_target, 6 * UPGRADE_THRESHOLD_PER_TIER)
        details = project.building_upgrade_details
        self.assertEqual(details.building, self.building)
        self.assertEqual(details.new_target_size, 6)
        self.assertIsNone(details.applied_at)

    def test_commission_owner_gated(self) -> None:
        with self.assertRaises(RoomBuildError):
            start_building_upgrade(
                persona=self.stranger,
                building=self.building,
                new_target_size=6,
            )

    def test_noop_upgrade_refused(self) -> None:
        # self.building.target_size is 5 (BuildingFactory default); targeting
        # the same tier is a no-op.
        with self.assertRaises(BuildingUpgradeError):
            start_building_upgrade(
                persona=self.owner,
                building=self.building,
                new_target_size=self.building.target_size,
            )

    def test_downgrade_refused(self) -> None:
        with self.assertRaises(BuildingUpgradeError):
            start_building_upgrade(
                persona=self.owner,
                building=self.building,
                new_target_size=self.building.target_size - 1,
            )

    def test_over_cap_refused(self) -> None:
        with self.assertRaises(BuildingUpgradeError):
            start_building_upgrade(
                persona=self.owner,
                building=self.building,
                new_target_size=MAX_BUILDING_SIZE_TIER + 1,
            )


class CompleteBuildingUpgradeTests(TestCase):
    def setUp(self) -> None:
        ensure_building_size_tiers()

    def test_raises_size_and_re_snapshots_budget_once(self) -> None:
        building = BuildingFactory(target_size=5, space_budget=1250)
        project = ProjectFactory()
        BuildingUpgradeDetailsFactory(project=project, building=building, new_target_size=6)
        complete_building_upgrade(project)
        building.refresh_from_db()
        self.assertEqual(building.target_size, 6)
        # tier 6 = Palace = 2500 units (from seeds.py)
        self.assertEqual(building.space_budget, 2500)

    def test_idempotent_on_second_call(self) -> None:
        building = BuildingFactory(target_size=5, space_budget=1250)
        project = ProjectFactory()
        details = BuildingUpgradeDetailsFactory(
            project=project, building=building, new_target_size=6
        )

        complete_building_upgrade(project)
        first_applied_at = details.__class__.objects.get(project=project).applied_at
        complete_building_upgrade(project)  # second call, same project
        second_applied_at = details.__class__.objects.get(project=project).applied_at
        self.assertEqual(first_applied_at, second_applied_at)
        # size unchanged by the no-op second call
        building.refresh_from_db()
        self.assertEqual(building.target_size, 6)

    def test_max_set_never_regresses(self) -> None:
        """A lower-target upgrade completing after a higher one is a no-op
        on the building — max-set semantics, mirroring fortification."""
        building = BuildingFactory(target_size=5, space_budget=1250)

        # First upgrade: 5 -> 7 (Citadel, 5000 units)
        first_project = ProjectFactory()
        BuildingUpgradeDetailsFactory(project=first_project, building=building, new_target_size=7)
        complete_building_upgrade(first_project)
        building.refresh_from_db()
        self.assertEqual(building.target_size, 7)
        self.assertEqual(building.space_budget, 5000)

        # Second upgrade targets size 6, but building is already 7.
        second_project = ProjectFactory()
        BuildingUpgradeDetailsFactory(project=second_project, building=building, new_target_size=6)
        complete_building_upgrade(second_project)
        building.refresh_from_db()
        # max(7, 6) = 7; space_budget untouched (no growth)
        self.assertEqual(building.target_size, 7)
        self.assertEqual(building.space_budget, 5000)
