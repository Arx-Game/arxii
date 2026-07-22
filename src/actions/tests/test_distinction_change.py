"""Tests for the sheet-update request Actions (#2628)."""

from __future__ import annotations

from django.test import TestCase


class SheetUpdateActionRegistrationTests(TestCase):
    def test_submit_action_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "submit_sheet_update" in ACTIONS_BY_KEY

    def test_review_action_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "review_sheet_update" in ACTIONS_BY_KEY

    def test_gm_award_still_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "gm_award_distinction" in ACTIONS_BY_KEY

    def test_old_actions_removed(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "authorize_distinction_change" not in ACTIONS_BY_KEY
        assert "accept_distinction_change" not in ACTIONS_BY_KEY
