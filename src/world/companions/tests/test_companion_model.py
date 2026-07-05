"""Tests for the Companion instance model (#672)."""

from __future__ import annotations

from django.test import TestCase

from world.companions.factories import CompanionFactory


class CompanionModelTests(TestCase):
    def test_is_active_when_not_released(self) -> None:
        companion = CompanionFactory()

        self.assertTrue(companion.is_active)
        self.assertIsNone(companion.released_at)

    def test_is_active_false_once_released(self) -> None:
        from django.utils import timezone

        companion = CompanionFactory()
        companion.released_at = timezone.now()
        companion.save(update_fields=["released_at"])

        self.assertFalse(companion.is_active)

    def test_str_includes_name_and_archetype(self) -> None:
        companion = CompanionFactory(name="Fang", archetype__name="Wolf")

        self.assertEqual(str(companion), "Fang (Wolf)")
