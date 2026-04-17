from django.test import TestCase

from flows.events.names import EventNames
from flows.models.events import Event


class EventMigrationTests(TestCase):
    def test_all_mvp_events_seeded(self) -> None:
        for name in EventNames.all():
            self.assertTrue(
                Event.objects.filter(name=name).exists(),
                f"Event '{name}' not seeded by migration",
            )

    def test_event_labels_human_readable(self) -> None:
        ev = Event.objects.get(name="damage_applied")
        self.assertIn("damage", ev.label.lower())
