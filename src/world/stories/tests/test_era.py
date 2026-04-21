from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from world.stories.constants import EraStatus
from world.stories.factories import EraFactory
from world.stories.models import Era


class EraModelTests(TestCase):
    def test_era_default_status_is_upcoming(self):
        era = Era(
            name="default_status_test",
            display_name="Default Status Test",
            season_number=99,
        )
        era.save()
        self.assertEqual(era.status, EraStatus.UPCOMING)

    def test_era_str_uses_display_name(self):
        era = EraFactory(
            name="season_1",
            display_name="Shadows and Light",
            season_number=1,
        )
        self.assertIn("Shadows and Light", str(era))
        self.assertIn("1", str(era))


class EraActiveConstraintTests(TransactionTestCase):
    """Isolated from TestCase so the IntegrityError doesn't corrupt a shared transaction."""

    def test_only_one_active_era_allowed(self):
        EraFactory(status=EraStatus.ACTIVE, name="era_a")
        with self.assertRaises(IntegrityError):
            EraFactory(status=EraStatus.ACTIVE, name="era_b")
