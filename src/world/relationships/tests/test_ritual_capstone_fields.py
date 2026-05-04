"""Tests for ritual-capstone storage fields (Spec B §12.1)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import RitualFactory
from world.relationships.factories import RelationshipCapstoneFactory


class RitualCapstoneFieldTests(TestCase):
    def test_default_is_not_ritual_capstone(self) -> None:
        cap = RelationshipCapstoneFactory()
        cap.refresh_from_db()
        self.assertFalse(cap.is_ritual_capstone)
        self.assertIsNone(cap.ritual)

    def test_can_be_marked_ritual_capstone_with_ritual(self) -> None:
        ritual = RitualFactory()
        cap = RelationshipCapstoneFactory(is_ritual_capstone=True, ritual=ritual)
        cap.refresh_from_db()
        self.assertTrue(cap.is_ritual_capstone)
        self.assertEqual(cap.ritual_id, ritual.id)
