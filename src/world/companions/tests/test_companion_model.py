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


class CompanionArchetypeIsMountTests(TestCase):
    """Tests for the is_mount field on CompanionArchetype (#1863)."""

    def test_is_mount_defaults_to_false(self) -> None:
        """New archetypes default to non-mount."""
        from world.companions.factories import CompanionArchetypeFactory

        archetype = CompanionArchetypeFactory()
        self.assertFalse(archetype.is_mount)

    def test_is_mount_can_be_set_true(self) -> None:
        """An archetype can be flagged as a mount."""
        from world.companions.factories import CompanionArchetypeFactory

        archetype = CompanionArchetypeFactory(is_mount=True)
        self.assertTrue(archetype.is_mount)
