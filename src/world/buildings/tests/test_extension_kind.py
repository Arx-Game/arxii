"""BUILDING_EXTENSION project kind (#670): commission + completion handler."""

from world.buildings.models import BuildingExtensionDetails
from world.buildings.room_constants import EXTENSION_THRESHOLD_PER_UNIT
from world.buildings.room_services import (
    RoomBuildError,
    complete_building_extension,
    start_building_extension,
)
from world.buildings.tests.test_room_services import RoomBuilderBase
from world.projects.constants import CompletionMode, ProjectKind


class StartBuildingExtensionTests(RoomBuilderBase):
    def test_commission_creates_project_and_details(self) -> None:
        project = start_building_extension(
            persona=self.owner, building=self.building, added_budget=50
        )
        self.assertEqual(project.kind, ProjectKind.BUILDING_EXTENSION)
        self.assertEqual(project.completion_mode, CompletionMode.SINGLE_THRESHOLD)
        self.assertEqual(project.threshold_target, 50 * EXTENSION_THRESHOLD_PER_UNIT)
        details = BuildingExtensionDetails.objects.get(project=project)
        self.assertEqual(details.building, self.building)
        self.assertEqual(details.added_budget, 50)
        self.assertIsNone(details.applied_at)

    def test_commission_owner_gated(self) -> None:
        with self.assertRaises(RoomBuildError):
            start_building_extension(persona=self.stranger, building=self.building, added_budget=50)

    def test_zero_budget_refused(self) -> None:
        with self.assertRaises(RoomBuildError):
            start_building_extension(persona=self.owner, building=self.building, added_budget=0)


class CompleteBuildingExtensionTests(RoomBuilderBase):
    def test_completion_raises_space_budget_once(self) -> None:
        project = start_building_extension(
            persona=self.owner, building=self.building, added_budget=50
        )
        from world.buildings.models import Building

        complete_building_extension(project)
        self.assertEqual(Building.objects.get(pk=self.building.pk).space_budget, 150)
        # Idempotent — the applied_at marker blocks a double-apply.
        complete_building_extension(project)
        self.assertEqual(Building.objects.get(pk=self.building.pk).space_budget, 150)
