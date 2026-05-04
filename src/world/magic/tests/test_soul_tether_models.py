"""Soul Tether model tests (Spec B §15)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import ThreadFactory


class ThreadHollowFieldTests(TestCase):
    def test_hollow_current_default_zero(self) -> None:
        thread = ThreadFactory()
        thread.refresh_from_db()
        self.assertEqual(thread.hollow_current, 0)

    def test_hollow_current_persists(self) -> None:
        thread = ThreadFactory()
        thread.hollow_current = 12
        thread.save(update_fields=["hollow_current"])
        thread.refresh_from_db()
        self.assertEqual(thread.hollow_current, 12)
