"""Tests for WebsocketMessageType enum coverage."""

from django.test import TestCase

from web.webclient.message_types import WebsocketMessageType


class WebsocketMessageTypeTests(TestCase):
    def test_puppet_changed_exists(self) -> None:
        assert WebsocketMessageType.PUPPET_CHANGED.value == "puppet_changed"
