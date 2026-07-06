"""Tests for CmdSearch — telnet face of the existing SearchAction (#1866)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.investigation import CmdSearch
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory


class CmdSearchTests(TestCase):
    def test_search_dispatches_search_action(self):
        room = ObjectDBFactory(db_key="CmdSearchRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="cmdsearch_account")
        caller = CharacterFactory(db_key="CmdSearchAlice", location=room)
        caller.db_account = account
        caller.save()

        cmd = CmdSearch()
        cmd.caller = caller
        cmd.args = ""
        cmd.raw_string = "search"
        messages: list[str] = []
        cmd.msg = lambda *a, **kw: messages.append(a[0] if a else "")  # noqa: ARG005

        with patch.object(
            CmdSearch.action.__class__,
            "run",
            return_value=ActionResult(success=True, message="You search the room."),
        ) as mocked:
            cmd.func()
        mocked.assert_called_once()
        assert messages == ["You search the room."]
