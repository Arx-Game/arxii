"""Neighborhood turf control (#2862). SQLite tier."""

from unittest.mock import patch

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.models import Area
from world.societies.models import NeighborhoodTurf, Organization, OrganizationType
from world.societies.turf_services import (
    FLIP_START_GRIP,
    apply_turf_push,
    area_crime_value,
)


class TurfPushTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_type = OrganizationType.objects.create(name="gang")
        cls.ashfingers = Organization.objects.create(name="The Ashfingers", org_type=cls.org_type)
        cls.crew = Organization.objects.create(name="The Crew", org_type=cls.org_type)

    def setUp(self):
        self.area = Area.objects.create(
            name=f"Warrens {self.id()}"[-60:], level=AreaLevel.NEIGHBORHOOD
        )

    def test_uncontested_push_claims_the_ground(self):
        turf = apply_turf_push(self.crew, self.area, 30)
        self.assertEqual(turf.controlling_org, self.crew)
        self.assertEqual(turf.grip, 30)

    def test_own_pushes_deepen_grip(self):
        apply_turf_push(self.crew, self.area, 30)
        turf = apply_turf_push(self.crew, self.area, 30)
        self.assertEqual(turf.grip, 60)

    def test_rival_pushes_erode_and_provoke(self):
        NeighborhoodTurf.objects.create(area=self.area, controlling_org=self.ashfingers, grip=50)
        with patch("world.societies.turf_services._open_retaliation") as retaliation:
            turf = apply_turf_push(self.crew, self.area, 20)
        self.assertEqual(turf.controlling_org, self.ashfingers)
        self.assertEqual(turf.grip, 30)
        retaliation.assert_called_once()

    def test_grip_breaking_flips_control(self):
        NeighborhoodTurf.objects.create(area=self.area, controlling_org=self.ashfingers, grip=15)
        with patch("world.societies.turf_services._open_retaliation") as retaliation:
            turf = apply_turf_push(self.crew, self.area, 20)
        self.assertEqual(turf.controlling_org, self.crew)
        self.assertEqual(turf.grip, FLIP_START_GRIP)
        # the provoked party is the PREVIOUS holder, not the new one
        self.assertEqual(retaliation.call_args.args[2], self.ashfingers)

    def test_grip_writes_the_area_crime_stat(self):
        apply_turf_push(self.crew, self.area, 60)
        self.assertEqual(area_crime_value(self.area), 30)

    def test_control_retargets_the_kickup_stream(self):
        from world.currency.constants import IncomeStreamKind
        from world.currency.models import OrgIncomeStream

        stream = OrgIncomeStream.objects.create(
            organization=self.ashfingers,
            name="Warrens kick-up",
            kind=IncomeStreamKind.CRIME_KICKUP,
            gross_amount=1000,
            area=self.area,
        )
        NeighborhoodTurf.objects.create(area=self.area, controlling_org=self.ashfingers, grip=10)
        with patch("world.societies.turf_services._open_retaliation"):
            apply_turf_push(self.crew, self.area, 20)
        stream.refresh_from_db()
        self.assertEqual(stream.organization, self.crew)

    def test_retaliation_opens_a_crisis_against_the_pusher(self):
        from world.seeds.underworld import _seed_retaliation_crisis_type
        from world.societies.houses.models import DomainCrisis

        _seed_retaliation_crisis_type()
        NeighborhoodTurf.objects.create(area=self.area, controlling_org=self.ashfingers, grip=50)
        apply_turf_push(self.crew, self.area, 10)
        crisis = DomainCrisis.objects.get()
        self.assertEqual(crisis.org, self.crew)
        self.assertEqual(crisis.crisis_type.name, "Gang Retaliation")


class GuardPressureScalingTest(TestCase):
    def test_crime_stat_scales_the_trigger_chance(self):
        import random

        from world.justice.pipeline import maybe_guard_encounter
        from world.scenes.factories import PersonaFactory

        area = Area.objects.create(name="Hot Corner", level=AreaLevel.NEIGHBORHOOD)
        org_type = OrganizationType.objects.create(name="gang")
        crew = Organization.objects.create(name="Crew", org_type=org_type)
        apply_turf_push(crew, area, 100)  # CRIME 50
        persona = PersonaFactory()
        rng = random.Random(7)  # noqa: S311 — game RNG in a test, not crypto
        with (
            patch("world.justice.pipeline.heat_value_for", return_value=1000),
            patch.dict("world.justice.pipeline._TRIGGER_PCT", {"room_arrival": 40}, clear=False),
            patch("world.justice.pipeline._TRIGGER_FLOOR", {"room_arrival": 0}),
            patch.object(rng, "random", return_value=0.55),
        ):
            # 0.55*100=55 >= 40 base would NOT fire; with +50% crime scale
            # (40*1.5=60) it does.
            encounter = maybe_guard_encounter(persona, area, "room_arrival", rng=rng)
        self.assertIsNotNone(encounter)
