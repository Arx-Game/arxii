"""Tests for Resonance gain config models."""

from django.test import TestCase

from world.magic.services.gain import get_resonance_gain_config


class EntryFlourishGrantConfigTest(TestCase):
    def test_entry_flourish_grant_defaults_to_10(self):
        cfg = get_resonance_gain_config()
        self.assertEqual(cfg.entry_flourish_grant, 10)
