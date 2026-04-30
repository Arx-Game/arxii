"""Tests for the ``execute_action`` websocket inputfunc.

The inputfunc is the unified web entry point for game mutations: the React
frontend sends an inbound ``execute_action`` message, the inputfunc resolves
the action key and any ``*_id`` kwargs to model instances, runs the action
on the session's puppeted character, and pushes back an ``ACTION_RESULT``
message. This module exercises the puppet/lookup/dispatch glue with mocks
so the contract stays stable as actions are added or modified.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionInterrupted, ActionResult
from server.conf.inputfuncs import execute_action
from web.webclient.message_types import WebsocketMessageType


def _make_session(puppet: object = None) -> MagicMock:
    """Build a stub session with a configurable ``puppet`` and recording ``msg``."""
    session = MagicMock()
    session.puppet = puppet
    return session


def _result_payload(session: MagicMock) -> dict:
    """Pull the kwargs payload from the most recent ``session.msg`` call."""
    assert session.msg.called, "session.msg was not called"
    return session.msg.call_args.kwargs


class ExecuteActionInputfuncTests(TestCase):
    """End-to-end behavior of the ``execute_action`` inputfunc."""

    def test_no_puppet_sends_error(self) -> None:
        """When session.puppet is None, an error response is sent and no action runs."""
        session = _make_session(puppet=None)
        with patch("actions.registry.get_action") as get_action:
            execute_action(session, action="equip", kwargs={})
        get_action.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("playing a character", payload["kwargs"]["message"])

    def test_missing_action_key_sends_error(self) -> None:
        """Inbound payload without an ``action`` key returns a structured error."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        with patch("actions.registry.get_action") as get_action:
            execute_action(session, kwargs={})
        get_action.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("No action specified", payload["kwargs"]["message"])

    def test_unknown_action_key_sends_error(self) -> None:
        """An unknown action key returns a structured error without dispatching."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        with patch("actions.registry.get_action", return_value=None):
            execute_action(session, action="not_a_real_action", kwargs={})
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("Unknown action", payload["kwargs"]["message"])
        self.assertIn("not_a_real_action", payload["kwargs"]["message"])

    def test_happy_path_runs_action_and_returns_result(self) -> None:
        """Valid action key + kwargs runs the action and forwards its result."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.run.return_value = ActionResult(
            success=True,
            message="You equip it.",
            data={"slot": "torso"},
        )
        with patch("actions.registry.get_action", return_value=stub_action):
            execute_action(session, action="equip", kwargs={"slot": "torso"})
        stub_action.run.assert_called_once_with(actor, slot="torso")
        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertEqual(payload["kwargs"]["success"], True)
        self.assertEqual(payload["kwargs"]["message"], "You equip it.")
        self.assertEqual(payload["kwargs"]["data"], {"slot": "torso"})

    def test_object_id_kwarg_is_resolved(self) -> None:
        """Keys ending in ``_id`` with int values are resolved via ObjectDB."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        target_obj = MagicMock(name="resolved_target")
        stub_action = MagicMock()
        stub_action.run.return_value = ActionResult(success=True)

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get", return_value=target_obj) as get,
        ):
            execute_action(session, action="give", kwargs={"target_id": 42})

        get.assert_called_once_with(pk=42)
        # The ``_id`` suffix is stripped before dispatch.
        stub_action.run.assert_called_once_with(actor, target=target_obj)

    def test_object_id_not_found_sends_error(self) -> None:
        """An unresolvable object id sends an error and does not run the action."""
        from evennia.objects.models import ObjectDB

        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch(
                "evennia.objects.models.ObjectDB.objects.get",
                side_effect=ObjectDB.DoesNotExist,
            ),
        ):
            execute_action(session, action="give", kwargs={"target_id": 9999999})

        stub_action.run.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("Object not found", payload["kwargs"]["message"])
        self.assertIn("target_id", payload["kwargs"]["message"])

    def test_action_interrupted_sends_error(self) -> None:
        """ActionInterrupted from action.run is forwarded as a failure response."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.run.side_effect = ActionInterrupted("A trigger blocked it.")

        with patch("actions.registry.get_action", return_value=stub_action):
            execute_action(session, action="equip", kwargs={})

        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertEqual(payload["kwargs"]["message"], "A trigger blocked it.")

    def test_non_int_id_kwarg_passes_through(self) -> None:
        """Keys ending in ``_id`` with non-int values are not resolved.

        The wire format is documented as int-only for ``*_id`` keys; anything
        else (e.g., a slug) is passed through unchanged. This guards against
        the resolver eating string-id-shaped values that the action can
        handle directly.
        """
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.run.return_value = ActionResult(success=True)

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get") as get,
        ):
            execute_action(session, action="custom", kwargs={"identifier_id": "some-slug"})

        get.assert_not_called()
        stub_action.run.assert_called_once_with(actor, identifier_id="some-slug")
