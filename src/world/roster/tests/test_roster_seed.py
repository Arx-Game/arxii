"""One seeding path, one row per shelf (#2728)."""

from django.test import TestCase

from world.roster.models import Roster
from world.roster.models.choices import ActivityRequirement, RosterType
from world.roster.seeds import ensure_rosters


class EnsureRostersTests(TestCase):
    def test_creates_every_roster_type_exactly_once(self):
        ensure_rosters()
        self.assertEqual(Roster.objects.count(), len(RosterType.values))
        for value in RosterType.values:
            self.assertEqual(Roster.objects.filter(roster_type=value).count(), 1)

    def test_is_idempotent(self):
        ensure_rosters()
        ensure_rosters()
        self.assertEqual(Roster.objects.count(), len(RosterType.values))

    def test_activity_requirement_is_set_so_the_sweep_is_reachable(self):
        """The sweep filters on this; leaving it at NONE made the feature inert."""
        rosters = ensure_rosters()
        self.assertEqual(rosters[RosterType.ACTIVE].activity_requirement, ActivityRequirement.HIGH)

    def test_npc_and_active_refuse_applications(self):
        rosters = ensure_rosters()
        self.assertFalse(rosters[RosterType.NPC].allow_applications)
        self.assertFalse(rosters[RosterType.ACTIVE].allow_applications)
        self.assertTrue(rosters[RosterType.AVAILABLE].allow_applications)
