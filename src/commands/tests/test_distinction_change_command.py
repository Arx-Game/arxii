"""CmdDistinctionChange telnet command (#2607 follow-up) — parsing, routing, hub."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.distinction_change import CmdDistinctionChange, _kv
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import DistinctionChangeAuthorization


def _build(caller, args: str = "") -> CmdDistinctionChange:
    cmd = CmdDistinctionChange()
    cmd.caller = caller
    cmd.args = args
    cmd.msg = MagicMock()
    return cmd


class KvParsingTests(TestCase):
    def test_parses_pairs(self) -> None:
        assert _kv("target_name=Bob action=add distinction_slug=silver") == {
            "target_name": "Bob",
            "action": "add",
            "distinction_slug": "silver",
        }


class RoutingTests(TestCase):
    def test_unknown_subverb_messages(self) -> None:
        sheet = CharacterSheetFactory()
        cmd = _build(sheet.character, "frobnicate x=1")
        cmd.func()
        assert "Unknown action" in cmd.msg.call_args[0][0]


class HubTests(TestCase):
    def test_hub_lists_pending_add_authorization(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(name="Silver Tongue")
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=sheet,
            action="add",
            target_distinction=distinction,
            reason="mentor",
            xp_cost=12,
        )

        cmd = _build(sheet.character, "")
        cmd.func()

        output = cmd.msg.call_args[0][0]
        assert f"#{auth.pk}" in output
        assert "Silver Tongue" in output
        assert "12 XP" in output
