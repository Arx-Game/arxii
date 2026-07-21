"""Tests for the distinction change authorization Actions (#2607)."""

from __future__ import annotations

from django.test import TestCase


class DistinctionChangeActionRegistrationTests(TestCase):
    def test_authorize_action_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "authorize_distinction_change" in ACTIONS_BY_KEY

    def test_accept_action_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "accept_distinction_change" in ACTIONS_BY_KEY
