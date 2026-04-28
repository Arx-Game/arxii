"""Tests for world.stories.services.era — era lifecycle service functions."""

from django.test import TestCase

from world.stories.constants import EraStatus
from world.stories.exceptions import EraAdvanceError
from world.stories.factories import EraFactory
from world.stories.models import Era
from world.stories.services.era import advance_era, archive_era


class AdvanceEraHappyPathTests(TestCase):
    """advance_era: closes current ACTIVE era and activates the UPCOMING one."""

    def test_advance_era_activates_upcoming(self) -> None:
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s2")
        result = advance_era(next_era=upcoming)
        upcoming.refresh_from_db()
        self.assertEqual(result.status, EraStatus.ACTIVE)
        self.assertEqual(upcoming.status, EraStatus.ACTIVE)
        self.assertIsNotNone(upcoming.activated_at)

    def test_advance_era_closes_current_active(self) -> None:
        active = EraFactory(status=EraStatus.ACTIVE, name="s1")
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s2")
        advance_era(next_era=upcoming)
        active.refresh_from_db()
        self.assertEqual(active.status, EraStatus.CONCLUDED)
        self.assertIsNotNone(active.concluded_at)

    def test_advance_era_works_when_no_current_active(self) -> None:
        """Initial activation: no ACTIVE era exists."""
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s1")
        result = advance_era(next_era=upcoming)
        self.assertEqual(result.status, EraStatus.ACTIVE)

    def test_advance_era_returns_updated_era(self) -> None:
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s2")
        result = advance_era(next_era=upcoming)
        self.assertEqual(result.pk, upcoming.pk)
        self.assertEqual(result.status, EraStatus.ACTIVE)


class AdvanceEraRejectionTests(TestCase):
    """advance_era: rejects non-UPCOMING eras."""

    def test_advance_era_rejects_active_era(self) -> None:
        active = EraFactory(status=EraStatus.ACTIVE, name="s1")
        with self.assertRaises(EraAdvanceError):
            advance_era(next_era=active)

    def test_advance_era_rejects_concluded_era(self) -> None:
        concluded = EraFactory(status=EraStatus.CONCLUDED, name="s0")
        with self.assertRaises(EraAdvanceError):
            advance_era(next_era=concluded)

    def test_advance_era_error_message_is_helpful(self) -> None:
        active = EraFactory(status=EraStatus.ACTIVE, name="s1")
        with self.assertRaises(EraAdvanceError) as ctx:
            advance_era(next_era=active)
        self.assertIn("UPCOMING", ctx.exception.user_message)


class AdvanceEraAtomicTests(TestCase):
    """advance_era: verify post-advance state is consistent."""

    def test_multiple_concluded_eras_allowed_after_advance(self) -> None:
        """Two advances should leave two CONCLUDED eras, no constraint violations."""
        era1 = EraFactory(status=EraStatus.ACTIVE, name="s1")
        era2 = EraFactory(status=EraStatus.UPCOMING, name="s2")
        era3 = EraFactory(status=EraStatus.UPCOMING, name="s3")

        advance_era(next_era=era2)
        era1.refresh_from_db()
        era2.refresh_from_db()
        self.assertEqual(era1.status, EraStatus.CONCLUDED)
        self.assertEqual(era2.status, EraStatus.ACTIVE)

        advance_era(next_era=era3)
        era2.refresh_from_db()
        era3.refresh_from_db()
        self.assertEqual(era2.status, EraStatus.CONCLUDED)
        self.assertEqual(era3.status, EraStatus.ACTIVE)

        concluded_count = Era.objects.filter(status=EraStatus.CONCLUDED).count()
        self.assertEqual(concluded_count, 2)


class ArchiveEraTests(TestCase):
    """archive_era: marks ACTIVE era CONCLUDED; idempotent on CONCLUDED."""

    def test_archive_active_era(self) -> None:
        era = EraFactory(status=EraStatus.ACTIVE, name="s1")
        result = archive_era(era=era)
        self.assertEqual(result.status, EraStatus.CONCLUDED)
        self.assertIsNotNone(result.concluded_at)

    def test_archive_active_era_persists(self) -> None:
        era = EraFactory(status=EraStatus.ACTIVE, name="s1")
        archive_era(era=era)
        era.refresh_from_db()
        self.assertEqual(era.status, EraStatus.CONCLUDED)

    def test_archive_concluded_era_is_idempotent(self) -> None:
        era = EraFactory(status=EraStatus.CONCLUDED, name="s0")
        era.concluded_at = None  # ensure we didn't set it
        era.save(update_fields=["concluded_at"])
        result = archive_era(era=era)
        # Status still CONCLUDED; concluded_at not touched again
        self.assertEqual(result.status, EraStatus.CONCLUDED)

    def test_archive_upcoming_era_raises(self) -> None:
        era = EraFactory(status=EraStatus.UPCOMING, name="s2")
        with self.assertRaises(EraAdvanceError):
            archive_era(era=era)

    def test_archive_upcoming_era_error_message(self) -> None:
        era = EraFactory(status=EraStatus.UPCOMING, name="s2")
        with self.assertRaises(EraAdvanceError) as ctx:
            archive_era(era=era)
        self.assertIn("UPCOMING", ctx.exception.user_message)
