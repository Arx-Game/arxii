"""Tests for MentorBondConfig singleton and related constants (#1165)."""

from django.test import TestCase

from world.covenants.factories import seed_mentor_bond_defaults
from world.covenants.services import get_mentor_bond_config


class MentorBondConfigTests(TestCase):
    def test_seed_creates_singleton_with_defaults(self):
        seed_mentor_bond_defaults()
        cfg = get_mentor_bond_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.band_width, 2)
        self.assertEqual(cfg.adjacency_offset, 1)
        self.assertIsNone(cfg.max_sidekicks_per_mentor)
