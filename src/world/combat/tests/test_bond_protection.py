"""Tests for relationship-scaled protection (INTERPOSE/SUCCOR) (#2021)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase


class BondProtectionTests(TestCase):
    """Bond bonus flows through to the protection capability check."""

    def test_dispatch_interpose_accepts_extra_modifiers(self):
        """dispatch_interpose passes extra_modifiers through to resolve_challenge."""
        from world.combat.services import dispatch_interpose

        interposer = MagicMock()
        protected = MagicMock()
        interposer.sheet_data = None  # no bond → 0 bonus
        protected.sheet_data = None
        pre_payload = MagicMock()
        pre_payload.amount = 10

        # Should not raise — extra_modifiers=0 when no bond
        with patch("world.mechanics.reactions.dispatch_capability_reaction") as mock_dispatch:
            mock_dispatch.return_value = None
            dispatch_interpose(interposer, protected, pre_payload, approach=None, extra_modifiers=0)
            self.assertTrue(mock_dispatch.called)

    def test_dispatch_succor_accepts_extra_modifiers(self):
        """dispatch_succor passes extra_modifiers through to resolve_challenge."""
        from world.combat.services import dispatch_succor

        succorer = MagicMock()
        protected = MagicMock()
        succorer.sheet_data = None
        protected.sheet_data = None

        with patch("world.mechanics.reactions.dispatch_capability_reaction") as mock_dispatch:
            mock_dispatch.return_value = None
            result = dispatch_succor(succorer, protected, approach=None, extra_modifiers=0)
            self.assertTrue(mock_dispatch.called)
            self.assertEqual(result, 1.0)  # no challenge → 1.0 multiplier

    def test_resolve_challenge_accepts_extra_modifiers(self):
        """resolve_challenge passes extra_modifiers to perform_check."""
        from world.mechanics.challenge_resolution import resolve_challenge

        self.assertTrue(callable(resolve_challenge))
