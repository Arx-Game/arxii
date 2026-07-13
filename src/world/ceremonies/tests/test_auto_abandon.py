"""Auto-abandon sweep tests (#2289, Decision 12)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.ceremonies.constants import CeremonyStatus
from world.ceremonies.factories import CeremonyFactory
from world.game_clock.tasks import abandon_stale_ceremonies


class AutoAbandonSweepTests(TestCase):
    def test_fresh_open_ceremony_is_untouched(self) -> None:
        ceremony = CeremonyFactory()
        abandon_stale_ceremonies()
        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.OPEN)

    def test_day_old_ceremony_is_abandoned(self) -> None:
        ceremony = CeremonyFactory()
        stale_time = timezone.now() - timedelta(days=2)
        type(ceremony).objects.filter(pk=ceremony.pk).update(opened_at=stale_time)
        abandon_stale_ceremonies()
        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.ABANDONED)

    def test_finished_scene_abandons_its_ceremony(self) -> None:
        from world.scenes.factories import SceneFactory

        scene = SceneFactory()
        ceremony = CeremonyFactory(scene=scene)
        scene.finish_scene()
        abandon_stale_ceremonies()
        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.ABANDONED)
