"""Tests for the FORTIFICATION_UPGRADE project kind (#1713)."""

from django.test import TestCase

from world.buildings.factories import BuildingFactory, FortificationUpgradeDetailsFactory
from world.buildings.fortification_services import (
    FortificationLevelExceedsMaximumError,
    complete_fortification_upgrade,
    start_fortification_upgrade,
)
from world.buildings.room_constants import MAX_FORTIFICATION_LEVEL
from world.projects.factories import ProjectFactory
from world.scenes.factories import PersonaFactory


class StartFortificationUpgradeTests(TestCase):
    def test_creates_project_and_details(self):
        building = BuildingFactory(fortification_level=0)
        persona = PersonaFactory()
        project = start_fortification_upgrade(persona=persona, building=building, target_level=2)
        self.assertEqual(project.fortification_upgrade_details.building_id, building.pk)
        self.assertEqual(project.fortification_upgrade_details.target_level, 2)

    def test_rejects_level_above_maximum(self):
        building = BuildingFactory(fortification_level=0)
        persona = PersonaFactory()
        with self.assertRaises(FortificationLevelExceedsMaximumError):
            start_fortification_upgrade(
                persona=persona, building=building, target_level=MAX_FORTIFICATION_LEVEL + 1
            )

    def test_rejects_level_not_exceeding_current(self):
        building = BuildingFactory(fortification_level=3)
        persona = PersonaFactory()
        with self.assertRaises(FortificationLevelExceedsMaximumError):
            start_fortification_upgrade(persona=persona, building=building, target_level=3)


class CompleteFortificationUpgradeTests(TestCase):
    def test_raises_building_level(self):
        building = BuildingFactory(fortification_level=0)
        project = ProjectFactory()
        FortificationUpgradeDetailsFactory(project=project, building=building, target_level=3)
        complete_fortification_upgrade(project)
        building.refresh_from_db()
        self.assertEqual(building.fortification_level, 3)

    def test_idempotent_on_second_call(self):
        building = BuildingFactory(fortification_level=0)
        project = ProjectFactory()
        details = FortificationUpgradeDetailsFactory(
            project=project, building=building, target_level=3
        )
        complete_fortification_upgrade(project)
        first_applied_at = details.__class__.objects.get(project=project).applied_at
        complete_fortification_upgrade(project)  # second call, same project
        second_applied_at = details.__class__.objects.get(project=project).applied_at
        self.assertEqual(first_applied_at, second_applied_at)

    def test_does_not_regress_a_higher_level(self):
        """A lower-target Project completing after a higher one already applied
        must not regress fortification_level (#1713 Decision 8)."""
        building = BuildingFactory(fortification_level=0)
        high_project = ProjectFactory()
        FortificationUpgradeDetailsFactory(project=high_project, building=building, target_level=4)
        complete_fortification_upgrade(high_project)

        low_project = ProjectFactory()
        FortificationUpgradeDetailsFactory(project=low_project, building=building, target_level=2)
        complete_fortification_upgrade(low_project)

        building.refresh_from_db()
        self.assertEqual(building.fortification_level, 4)
