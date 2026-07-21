"""CmdTableRequest telnet command (#2607) — parsing, routing, and hub."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.table_requests import CmdTableRequest, _kv
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionChangeRequestFactory
from world.gm.factories import GMTableMembershipFactory, TableUpdateRequestFactory
from world.scenes.factories import PersonaFactory


def _build(caller, args: str = "") -> CmdTableRequest:
    cmd = CmdTableRequest()
    cmd.caller = caller
    cmd.args = args
    cmd.msg = MagicMock()
    return cmd


class KvParsingTests(TestCase):
    def test_parses_key_value_pairs(self) -> None:
        assert _kv("table_id=3 distinction_slug=silver-tongue removing=1") == {
            "table_id": "3",
            "distinction_slug": "silver-tongue",
            "removing": "1",
        }

    def test_ignores_tokens_without_equals(self) -> None:
        assert _kv("stray request_id=7") == {"request_id": "7"}


class RoutingTests(TestCase):
    def test_unknown_subverb_messages(self) -> None:
        sheet = CharacterSheetFactory()
        cmd = _build(sheet.character, "frobnicate x=1")
        cmd.func()
        assert "Unknown action" in cmd.msg.call_args[0][0]


class HubTests(TestCase):
    def test_hub_lists_the_members_open_request(self) -> None:
        sheet = CharacterSheetFactory()
        membership = GMTableMembershipFactory(persona=PersonaFactory(character_sheet=sheet))
        request = TableUpdateRequestFactory(membership=membership)
        DistinctionChangeRequestFactory(request=request)

        cmd = _build(sheet.character, "")
        cmd.func()

        output = cmd.msg.call_args[0][0]
        assert f"#{request.pk}" in output
        assert "Your open requests" in output
