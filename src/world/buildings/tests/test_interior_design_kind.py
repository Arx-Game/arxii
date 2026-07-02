"""INTERIOR_DESIGN project kind (#670): commission, prereqs, polish application."""

from world.buildings.models import (
    BuildingPolish,
    BuildingProjectInstance,
    InteriorDesignDetails,
    PolishCategory,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
    RoomPolish,
    TierThreshold,
)
from world.buildings.room_services import (
    RoomBuildError,
    commission_decoration,
    complete_interior_design,
    remove_room,
)
from world.buildings.tests.test_room_services import RoomBuilderBase
from world.projects.constants import ProjectKind


class InteriorDesignBase(RoomBuilderBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.opulence = PolishCategory.objects.create(name="Opulence")
        cls.elegance = PolishCategory.objects.create(name="Elegance")
        cls.template = ProjectTemplate.objects.create(
            name="Marble Foyer",
            base_cost=500,
            project_kind=ProjectKind.INTERIOR_DESIGN,
        )
        ProjectTemplatePolishIncrement.objects.create(
            template=cls.template, category=cls.opulence, value=800
        )
        ProjectTemplatePolishIncrement.objects.create(
            template=cls.template, category=cls.elegance, value=200
        )


class CommissionDecorationTests(InteriorDesignBase):
    def test_commission_creates_project_and_details(self) -> None:
        project = commission_decoration(
            persona=self.owner, building=self.building, template=self.template
        )
        self.assertEqual(project.kind, ProjectKind.INTERIOR_DESIGN)
        self.assertEqual(project.threshold_target, 500)
        details = InteriorDesignDetails.objects.get(project=project)
        self.assertIsNone(details.room)

    def test_commission_owner_gated(self) -> None:
        with self.assertRaises(RoomBuildError):
            commission_decoration(
                persona=self.stranger, building=self.building, template=self.template
            )

    def test_commission_checks_template_tier_prereqs(self) -> None:
        gated = ProjectTemplate.objects.create(name="Gilded Gallery", base_cost=900)
        gated.tier_prerequisites.add(
            TierThreshold.objects.create(category=self.opulence, tier_name="Notable", min_value=500)
        )
        with self.assertRaises(RoomBuildError) as caught:
            commission_decoration(persona=self.owner, building=self.building, template=gated)
        self.assertIn("Notable", caught.exception.user_message)
        BuildingPolish.objects.create(building=self.building, category=self.opulence, value=600)
        commission_decoration(persona=self.owner, building=self.building, template=gated)


class CompleteInteriorDesignTests(InteriorDesignBase):
    def test_building_target_completion_applies_polish(self) -> None:
        project = commission_decoration(
            persona=self.owner, building=self.building, template=self.template
        )
        complete_interior_design(project)
        self.assertTrue(
            BuildingProjectInstance.objects.filter(
                building=self.building, source_project=project
            ).exists()
        )
        # Idempotent.
        complete_interior_design(project)
        self.assertEqual(BuildingProjectInstance.objects.filter(building=self.building).count(), 1)

    def test_room_target_applies_room_polish(self) -> None:
        project = commission_decoration(
            persona=self.owner,
            building=self.building,
            template=self.template,
            room=self.entry.objectdb,
        )
        complete_interior_design(project)
        self.assertEqual(RoomPolish.objects.get(room=self.entry, category=self.opulence).value, 800)
        self.assertEqual(RoomPolish.objects.get(room=self.entry, category=self.elegance).value, 200)

    def test_remove_room_blocked_by_active_design_project(self) -> None:
        from world.buildings.room_services import dig_room

        profile = dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="north",
            name="Salon",
        )
        commission_decoration(
            persona=self.owner,
            building=self.building,
            template=self.template,
            room=profile.objectdb,
        )
        with self.assertRaises(RoomBuildError):
            remove_room(persona=self.owner, room=profile.objectdb)
