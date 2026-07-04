"""Tests for the BUILDING_RENOVATION project kind (#1858).

Owner-gated ``start_building_renovation`` tests use ``RoomBuilderBase`` (which
sets up an owned building) and are tagged ``postgres`` because the owner-gate
walks the ``AreaClosure`` materialized view. Completion-handler tests bypass
``is_owner`` (they build details directly via the factory) and so run on the
SQLite fast tier too.
"""

from django.test import TestCase, tag

from world.buildings.factories import (
    BuildingFactory,
    BuildingKindFactory,
    BuildingRenovationDetailsFactory,
)
from world.buildings.renovation_services import (
    complete_building_renovation,
    start_building_renovation,
)
from world.buildings.room_constants import RENOVATION_THRESHOLD
from world.buildings.room_services import RoomBuildError
from world.buildings.tests.test_room_services import RoomBuilderBase
from world.projects.constants import CompletionMode, ProjectKind
from world.projects.factories import ProjectFactory


@tag("postgres")  # start_building_renovation's is_owner gate walks AreaClosure
class StartBuildingRenovationTests(RoomBuilderBase):
    def test_commission_creates_project_and_details(self) -> None:
        target_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)
        project = start_building_renovation(
            persona=self.owner, building=self.building, target_kind=target_kind
        )
        self.assertEqual(project.kind, ProjectKind.BUILDING_RENOVATION)
        self.assertEqual(project.completion_mode, CompletionMode.SINGLE_THRESHOLD)
        self.assertEqual(project.threshold_target, RENOVATION_THRESHOLD)
        details = project.building_renovation_details
        self.assertEqual(details.building, self.building)
        self.assertEqual(details.target_kind, target_kind)
        self.assertIsNone(details.applied_at)

    def test_commission_owner_gated(self) -> None:
        target_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)
        with self.assertRaises(RoomBuildError):
            start_building_renovation(
                persona=self.stranger, building=self.building, target_kind=target_kind
            )

    def test_noop_renovation_refused(self) -> None:
        # self.building.kind is already the building's kind; targeting it is a no-op.
        with self.assertRaises(RoomBuildError):
            start_building_renovation(
                persona=self.owner, building=self.building, target_kind=self.building.kind
            )


class CompleteBuildingRenovationTests(TestCase):
    def test_re_points_kind_once(self) -> None:
        building = BuildingFactory()
        target_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)
        project = ProjectFactory()
        BuildingRenovationDetailsFactory(
            project=project, building=building, target_kind=target_kind
        )
        complete_building_renovation(project)
        building.refresh_from_db()
        self.assertEqual(building.kind, target_kind)

    def test_idempotent_on_second_call(self) -> None:
        building = BuildingFactory()
        target_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)
        project = ProjectFactory()
        details = BuildingRenovationDetailsFactory(
            project=project, building=building, target_kind=target_kind
        )
        original_kind = building.kind

        complete_building_renovation(project)
        first_applied_at = details.__class__.objects.get(project=project).applied_at
        complete_building_renovation(project)  # second call, same project
        second_applied_at = details.__class__.objects.get(project=project).applied_at
        self.assertEqual(first_applied_at, second_applied_at)
        # kind unchanged by the no-op second call
        building.refresh_from_db()
        self.assertEqual(building.kind, target_kind)
        self.assertNotEqual(building.kind, original_kind)

    def test_later_renovation_can_re_point_back(self) -> None:
        """No ordering guard (unlike fortification): a later renovation may
        re-point to any target kind, including back to the original."""
        building = BuildingFactory()
        original_kind = building.kind
        occult_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)

        first_project = ProjectFactory()
        BuildingRenovationDetailsFactory(
            project=first_project, building=building, target_kind=occult_kind
        )
        complete_building_renovation(first_project)
        building.refresh_from_db()
        self.assertEqual(building.kind, occult_kind)

        # A second renovation re-points back to the original kind.
        second_project = ProjectFactory()
        BuildingRenovationDetailsFactory(
            project=second_project, building=building, target_kind=original_kind
        )
        complete_building_renovation(second_project)
        building.refresh_from_db()
        self.assertEqual(building.kind, original_kind)
