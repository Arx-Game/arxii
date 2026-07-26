"""RosterType is the single vocabulary for roster identity (#2728)."""

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from world.roster.models import Roster
from world.roster.models.choices import RosterType


class RosterTypeVocabularyTests(SimpleTestCase):
    def test_covers_every_shelf_a_character_can_sit_on(self):
        """Pending and NPC were real shelves living outside the enum."""
        self.assertEqual(
            set(RosterType.values),
            {"Active", "Inactive", "Available", "Restricted", "Frozen", "Pending", "NPC"},
        )

    def test_pending_and_npc_are_addressable(self):
        self.assertEqual(RosterType.PENDING, "Pending")
        self.assertEqual(RosterType.NPC, "NPC")


class RosterTypeKeyTests(TestCase):
    def test_roster_type_is_unique(self):
        """One row per shelf — this is what stopped the duplicate seeds."""
        Roster.objects.create(name="Active Characters", roster_type=RosterType.ACTIVE)
        with self.assertRaises(IntegrityError):
            Roster.objects.create(name="Active", roster_type=RosterType.ACTIVE)

    def test_name_is_free_text_and_not_the_key(self):
        """Display label may differ from the key without creating a second shelf."""
        roster = Roster.objects.create(
            name="Currently Played Characters", roster_type=RosterType.ACTIVE
        )
        self.assertEqual(roster.roster_type, RosterType.ACTIVE)
        self.assertNotEqual(roster.name, roster.roster_type)
