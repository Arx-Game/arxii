"""Tests for the same-connection room-state recovery inputfunc."""

from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from flows.types import RoomStateSendResult
from server.conf.inputfuncs import request_room_state


class RoomStateResyncInputfuncTests(SimpleTestCase):
    """Validate requester-only correlation and replay behavior."""

    def setUp(self):
        self.session = SimpleNamespace(msg=Mock(), ndb=SimpleNamespace())
        self.actor = SimpleNamespace(
            has_account=True,
            location=object(),
            sessions=SimpleNamespace(all=lambda: [self.session]),
            send_room_state=Mock(
                return_value=RoomStateSendResult(
                    sent=True,
                    room_dbref="#12",
                    room_id=12,
                    scene_id=4,
                    state_epoch="epoch",
                    state_sequence=9,
                )
            ),
        )
        self.session.puppet = self.actor
        self.request_id = "550e8400-e29b-41d4-a716-446655440000"

    def test_success_sends_snapshot_and_ack_to_requesting_session(self):
        request_room_state(self.session, client_request_id=self.request_id)

        self.actor.send_room_state.assert_called_once_with(
            session=self.session, resync_request_id=self.request_id
        )
        self.assertEqual(self.session.msg.call_count, 1)
        self.assertIn("state_resync", self.session.msg.call_args.kwargs)

    def test_duplicate_is_rejected_without_serialization(self):
        request_room_state(self.session, client_request_id=self.request_id)
        self.session.msg.reset_mock()

        request_room_state(self.session, client_request_id=self.request_id)

        self.actor.send_room_state.assert_called_once()
        payload = self.session.msg.call_args.kwargs["state_resync_error"][1]
        self.assertEqual(payload["code"], "duplicate_request")
