"""Tests for voyage actions (#1855)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.voyages import (
    AbandonVoyageAction,
    AdvanceLegAction,
    CompleteVoyageAction,
    DepartVoyageAction,
    InviteToVoyageAction,
    RespondVoyageInviteAction,
    StartVoyageAction,
)


class StartVoyageActionTests(TestCase):
    def test_returns_failure_without_destination(self):
        actor = MagicMock()
        with patch("actions.definitions.voyages._resolve_active_persona", return_value=None):
            result = StartVoyageAction().execute(actor)
        self.assertFalse(result.success)


class AdvanceLegActionTests(TestCase):
    def test_returns_failure_without_active_voyage(self):
        actor = MagicMock()
        persona = MagicMock()
        with (
            patch("actions.definitions.voyages._resolve_active_persona", return_value=persona),
            patch("actions.definitions.voyages._get_active_voyage", return_value=None),
        ):
            result = AdvanceLegAction().execute(actor)
        self.assertFalse(result.success)


class CompleteVoyageActionTests(TestCase):
    def test_returns_failure_without_active_voyage(self):
        actor = MagicMock()
        persona = MagicMock()
        with (
            patch("actions.definitions.voyages._resolve_active_persona", return_value=persona),
            patch("actions.definitions.voyages._get_active_voyage", return_value=None),
        ):
            result = CompleteVoyageAction().execute(actor)
        self.assertFalse(result.success)


class AbandonVoyageActionTests(TestCase):
    def test_returns_failure_without_active_voyage(self):
        actor = MagicMock()
        persona = MagicMock()
        with (
            patch("actions.definitions.voyages._resolve_active_persona", return_value=persona),
            patch("actions.definitions.voyages._get_active_voyage", return_value=None),
        ):
            result = AbandonVoyageAction().execute(actor)
        self.assertFalse(result.success)


class InviteToVoyageActionTests(TestCase):
    def test_returns_failure_without_target(self):
        actor = MagicMock()
        result = InviteToVoyageAction().execute(actor)
        self.assertFalse(result.success)


class RespondVoyageInviteActionTests(TestCase):
    def test_returns_failure_without_invite(self):
        actor = MagicMock()
        result = RespondVoyageInviteAction().execute(actor)
        self.assertFalse(result.success)


class DepartVoyageActionTests(TestCase):
    def test_returns_failure_without_voyage(self):
        actor = MagicMock()
        persona = MagicMock()
        with (
            patch("actions.definitions.voyages._resolve_active_persona", return_value=persona),
            patch("actions.definitions.voyages._get_active_voyage", return_value=None),
        ):
            result = DepartVoyageAction().execute(actor)
        self.assertFalse(result.success)
