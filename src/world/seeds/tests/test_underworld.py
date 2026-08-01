"""Underworld seed (#2862). SQLite tier — SEED_SAMPLE_CONTENT on for content rows."""

from django.test import TestCase, override_settings


@override_settings(SEED_SAMPLE_CONTENT=True)
class UnderworldSeedTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.security_checks import seed_security_check_content
        from world.seeds.social_checks import seed_social_check_content
        from world.seeds.underworld import seed_underworld_demo

        seed_check_resolution_tables()
        seed_security_check_content()
        seed_social_check_content()
        seed_underworld_demo()

    def test_gang_turf_stage_is_set(self):
        from world.societies.models import NeighborhoodTurf, Organization

        gang = Organization.objects.get(name__startswith="The Ashfingers")
        turf = NeighborhoodTurf.objects.get()
        self.assertEqual(turf.controlling_org, gang)
        self.assertEqual(turf.grip, 60)

    def test_retaliation_crisis_type_has_all_three_options(self):
        from world.societies.houses.models import DomainCrisisType

        crisis_type = DomainCrisisType.objects.get(name="Gang Retaliation")
        kinds = set(crisis_type.options.values_list("kind", flat=True))
        self.assertEqual(kinds, {"pay", "wait", "mission"})

    def test_criminal_missions_seed_restricted_with_categories(self):
        from world.missions.constants import MissionVisibility
        from world.missions.models import MissionCategory, MissionTemplate

        templates = MissionTemplate.objects.filter(name__in=[row[0] for row in _mission_names()])
        self.assertEqual(templates.count(), 7)
        for template in templates:
            self.assertEqual(template.visibility, MissionVisibility.RESTRICTED)
            self.assertTrue(template.availability_rule)
            self.assertGreaterEqual(template.categories.count(), 1)
        self.assertEqual(
            set(MissionCategory.objects.values_list("name", flat=True)),
            {"Crime", "Smuggling", "Turf War"},
        )

    def test_covert_board_carries_the_chain(self):
        from world.missions.models import MissionGiver

        giver = MissionGiver.objects.get(name__startswith="The Back Room Wall")
        self.assertEqual(giver.templates.count(), 7)

    def test_turf_missions_carry_project_lines(self):
        from world.missions.constants import DeedRewardSink
        from world.missions.models import MissionOptionRouteReward, MissionTemplate

        template = MissionTemplate.objects.get(name="Send a Message")
        rewards = MissionOptionRouteReward.objects.filter(
            route__option__node__template=template,
            sink=DeedRewardSink.PROJECT,
        )
        self.assertGreaterEqual(rewards.count(), 1)

    def test_failure_tiers_carry_crime_watch_heat(self):
        from world.missions.constants import DeedRewardSink
        from world.missions.models import MissionOptionRouteReward, MissionTemplate

        template = MissionTemplate.objects.get(name="The First Run")
        rewards = MissionOptionRouteReward.objects.filter(
            route__option__node__template=template,
            sink=DeedRewardSink.CRIME_WATCH,
        )
        self.assertGreaterEqual(rewards.count(), 1)
        self.assertTrue(all(r.ref == "smuggling" for r in rewards))

    def test_standing_route_bridges_both_engines(self):
        from world.tasking.models import TaskTemplate

        task = TaskTemplate.objects.get(name__startswith="Run the Quiet Docks")
        self.assertEqual(task.mission_template.name, "The Quiet Docks")
        self.assertEqual(task.category, "crime")
        self.assertGreaterEqual(task.outcome_routes.count(), 2)


def _mission_names():
    from world.seeds.underworld import _MISSION_ROWS

    return _MISSION_ROWS
