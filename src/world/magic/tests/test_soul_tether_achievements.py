"""Soul Tether achievement stat integration tests (Spec B §14.3, Phase 12).

Tests that Soul Tether services fire correct stat increments.
"""

from django.test import TestCase

from world.achievements.models import StatDefinition, StatTracker
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import wire_soul_tether_content
from world.magic.services.soul_tether import _increment_stat_safe


class SoulTetherStatDefinitionsTestCase(TestCase):
    """Test that all required stat definitions are seeded."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Seed all Soul Tether content."""
        wire_soul_tether_content()

    def test_sineating_units_accepted_stat_exists(self) -> None:
        """Test that sineating.units_accepted StatDefinition exists."""
        stat = StatDefinition.objects.get(key="sineating.units_accepted")
        self.assertEqual(stat.name, "Sins Eaten")
        self.assertIn("corruption", stat.description.lower())

    def test_sineating_units_declined_stat_exists(self) -> None:
        """Test that sineating.units_declined StatDefinition exists."""
        stat = StatDefinition.objects.get(key="sineating.units_declined")
        self.assertEqual(stat.name, "Sineating Requests Declined")

    def test_sineating_requests_made_stat_exists(self) -> None:
        """Test that sineating.requests_made StatDefinition exists."""
        stat = StatDefinition.objects.get(key="sineating.requests_made")
        self.assertEqual(stat.name, "Sineating Requests Made")

    def test_rescue_performed_stat_exists(self) -> None:
        """Test that rescue.performed StatDefinition exists."""
        stat = StatDefinition.objects.get(key="rescue.performed")
        self.assertEqual(stat.name, "Soul Tether Rescues Performed")

    def test_rescue_stage5_save_stat_exists(self) -> None:
        """Test that rescue.stage5_save StatDefinition exists."""
        stat = StatDefinition.objects.get(key="rescue.stage5_save")
        self.assertEqual(stat.name, "Subsumption Saves")

    def test_rescue_severity_reduced_stat_exists(self) -> None:
        """Test that rescue.severity_reduced StatDefinition exists."""
        stat = StatDefinition.objects.get(key="rescue.severity_reduced")
        self.assertEqual(stat.name, "Corruption Severity Reduced")

    def test_tether_formed_stat_exists(self) -> None:
        """Test that tether.formed StatDefinition exists."""
        stat = StatDefinition.objects.get(key="tether.formed")
        self.assertEqual(stat.name, "Soul Tethers Formed")

    def test_all_7_stats_exist(self) -> None:
        """Test that all 7 required stats are seeded."""
        keys = [
            "sineating.units_accepted",
            "sineating.units_declined",
            "sineating.requests_made",
            "rescue.performed",
            "rescue.stage5_save",
            "rescue.severity_reduced",
            "tether.formed",
        ]
        for key in keys:
            with self.subTest(key=key):
                stat = StatDefinition.objects.get(key=key)
                self.assertIsNotNone(stat)


class StatIncrementSafetyTestCase(TestCase):
    """Test that _increment_stat_safe handles missing StatDefinition gracefully."""

    def test_increment_stat_safe_no_op_on_missing_definition(self) -> None:
        """Test that _increment_stat_safe does not crash when StatDefinition is missing."""
        sheet = CharacterSheetFactory()

        # Call with a non-existent stat key — should no-op without raising
        try:
            _increment_stat_safe(sheet, "nonexistent.stat.key", 5)
        except StatDefinition.DoesNotExist:
            self.fail("_increment_stat_safe raised DoesNotExist for missing definition")

        # Verify no stat tracker was created
        self.assertFalse(StatTracker.objects.filter(character_sheet=sheet).exists())

    def test_increment_stat_safe_increments_when_definition_exists(self) -> None:
        """Test that _increment_stat_safe increments when StatDefinition exists."""
        sheet = CharacterSheetFactory()
        stat_def = StatDefinition.objects.create(
            key="test.stat",
            name="Test Stat",
            description="For testing",
        )

        # Increment multiple times
        _increment_stat_safe(sheet, "test.stat", 3)
        _increment_stat_safe(sheet, "test.stat", 2)

        # Verify tracker was created and has correct value
        tracker = StatTracker.objects.get(character_sheet=sheet, stat=stat_def)
        self.assertEqual(tracker.value, 5)

    def test_increment_stat_safe_with_factory_created_stats(self) -> None:
        """Test that _increment_stat_safe works with factory-created stats."""
        wire_soul_tether_content()  # Creates all 7 stats
        sheet = CharacterSheetFactory()

        # Increment each stat
        _increment_stat_safe(sheet, "sineating.units_accepted", 5)
        _increment_stat_safe(sheet, "sineating.units_declined", 1)
        _increment_stat_safe(sheet, "sineating.requests_made", 2)
        _increment_stat_safe(sheet, "rescue.performed", 1)
        _increment_stat_safe(sheet, "rescue.stage5_save", 1)
        _increment_stat_safe(sheet, "rescue.severity_reduced", 10)
        _increment_stat_safe(sheet, "tether.formed", 1)

        # Verify all trackers were created with correct values
        trackers = StatTracker.objects.filter(character_sheet=sheet)
        self.assertEqual(trackers.count(), 7)

        self.assertEqual(
            trackers.get(stat__key="sineating.units_accepted").value,
            5,
        )
        self.assertEqual(
            trackers.get(stat__key="sineating.units_declined").value,
            1,
        )
        self.assertEqual(
            trackers.get(stat__key="sineating.requests_made").value,
            2,
        )
        self.assertEqual(
            trackers.get(stat__key="rescue.performed").value,
            1,
        )
        self.assertEqual(
            trackers.get(stat__key="rescue.stage5_save").value,
            1,
        )
        self.assertEqual(
            trackers.get(stat__key="rescue.severity_reduced").value,
            10,
        )
        self.assertEqual(
            trackers.get(stat__key="tether.formed").value,
            1,
        )
