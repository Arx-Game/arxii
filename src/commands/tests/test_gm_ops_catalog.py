"""Telnet tests for ``gm suggest`` on ``CmdGMDashboard`` (#2127).

Thin parsing + ``action.run()`` over ``SubmitCatalogSuggestionAction`` --
these tests exercise the telnet-layer grammar (usage errors, subverb
routing); the full permission/tier matrix is covered by
``actions/tests/test_gm_catalog_actions.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.gm_ops import CmdGMDashboard
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import CatalogSuggestionProposalKind, GMLevel
from world.gm.factories import GMProfileFactory
from world.gm.models import CatalogSuggestion
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _room(*, db_key: str = "GMOpsCatalogRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _gm_in_room(room: object, level: str, *, db_key: str) -> object:
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    GMProfileFactory(account=tenure.player_data.account, level=level)
    char.db_account = tenure.player_data.account
    char.msg = MagicMock()
    return char


def _player_in_room(room: object, *, db_key: str) -> object:
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    char.msg = MagicMock()
    return char


def _run_cmd(caller: object, args: str) -> list[str]:
    cmd = CmdGMDashboard()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gm {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdGMSuggestTests(TestCase):
    def setUp(self) -> None:
        self.room = _room()
        self.gm_actor = _gm_in_room(self.room, GMLevel.STARTING, db_key="SuggestGM")
        self.player_actor = _player_in_room(self.room, db_key="SuggestPlayer")

    def test_suggest_creates_catalog_suggestion(self) -> None:
        messages = _run_cmd(self.gm_actor, "suggest new_situation=A dockside smuggling scene.")
        self.assertTrue(messages)
        self.assertTrue(any("submitted" in m.lower() for m in messages))
        self.assertEqual(CatalogSuggestion.objects.count(), 1)
        suggestion = CatalogSuggestion.objects.get()
        self.assertEqual(suggestion.proposal_kind, CatalogSuggestionProposalKind.NEW_SITUATION)
        self.assertIn("dockside", suggestion.proposal_text)

    def test_suggest_missing_equals_shows_usage(self) -> None:
        messages = _run_cmd(self.gm_actor, "suggest not a valid grammar")
        self.assertTrue(any("Usage: gm suggest" in m for m in messages))
        self.assertEqual(CatalogSuggestion.objects.count(), 0)

    def test_suggest_below_tier_is_refused(self) -> None:
        messages = _run_cmd(self.gm_actor, "suggest pool_guide=Use the Mishap pool.")
        self.assertTrue(messages)
        self.assertFalse(any("submitted" in m.lower() for m in messages))
        self.assertEqual(CatalogSuggestion.objects.count(), 0)

    def test_non_gm_is_refused(self) -> None:
        messages = _run_cmd(self.player_actor, "suggest other=Anything at all.")
        self.assertTrue(messages)
        self.assertEqual(CatalogSuggestion.objects.count(), 0)
