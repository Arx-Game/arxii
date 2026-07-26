"""RosterType is the single vocabulary for roster identity (#2728)."""

from django.test import SimpleTestCase

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
