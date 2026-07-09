"""Tests for CmdGrantItem (#707), gated on JUNIOR-tier GM trust or staff (#2117).

Mirrors the ``caller.search`` mock pattern used across the command tests
(e.g. ``test_relationships_command.py``): the caller is a real
``CharacterFactory`` instance with ``search``/``msg`` monkey-patched onto
the instance, and the target is a real character so ``target.sheet_data``
resolves for real.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.grant_item import CmdGrantItem
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.items.factories import ItemTemplateFactory
from world.items.models import ItemInstance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _build_cmd(caller, args: str = "") -> CmdGrantItem:
    cmd = CmdGrantItem()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"grant_item {args}".strip()
    return cmd


def _make_gm(character, level: str) -> None:
    """Attach a live roster tenure + GMProfile at ``level`` to ``character``."""
    CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet__character=character)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    GMProfileFactory(account=tenure.player_data.account, level=level)


class CmdGrantItemTests(TestCase):
    def setUp(self) -> None:
        self.staff_character = CharacterFactory()
        self.staff_character.msg = MagicMock()
        self.staff_character.search = MagicMock()
        self.staff_character.db_account = AccountFactory(is_staff=True)
        self.staff_character.save()
        self.target_character = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target_character)
        self.template = ItemTemplateFactory(name="Hand of the Betrayer")
        self.staff_character.search.return_value = self.target_character

    def test_grants_item_to_target_character(self) -> None:
        cmd = _build_cmd(
            self.staff_character,
            f"{self.target_character.key}=Hand of the Betrayer",
        )
        cmd.func()

        assert ItemInstance.objects.filter(
            template=self.template, holder_character_sheet=self.target_sheet
        ).exists()
        self.staff_character.msg.assert_called_with(
            f"Granted 'Hand of the Betrayer' to {self.target_character.key}."
        )

    def test_unknown_template_reports_error(self) -> None:
        cmd = _build_cmd(
            self.staff_character,
            f"{self.target_character.key}=Nonexistent Item",
        )
        cmd.func()

        self.staff_character.msg.assert_called()
        assert not ItemInstance.objects.filter(holder_character_sheet=self.target_sheet).exists()

    def test_target_with_no_sheet_reports_error(self) -> None:
        no_sheet_character = CharacterFactory()
        self.staff_character.search.return_value = no_sheet_character
        cmd = _build_cmd(
            self.staff_character,
            f"{no_sheet_character.key}=Hand of the Betrayer",
        )
        cmd.func()

        self.staff_character.msg.assert_called_with("That is not a character.")
        assert not ItemInstance.objects.filter(template=self.template).exists()

    def test_missing_equals_reports_usage(self) -> None:
        cmd = _build_cmd(self.staff_character, "justaname")
        cmd.func()

        # ArxCommand's default func() (now used, since action is no longer None)
        # sends both the plain-text message and a structured command_error payload.
        self.staff_character.msg.assert_any_call(
            "Usage: grant_item <character>=<item template name>"
        )

    def test_search_none_does_not_message_twice(self) -> None:
        self.staff_character.search.return_value = None
        cmd = _build_cmd(
            self.staff_character,
            "Nobody=Hand of the Betrayer",
        )
        cmd.func()

        self.staff_character.msg.assert_not_called()


class CmdGrantItemGMTrustTests(TestCase):
    """Trust-tier journeys for the JUNIOR-tier GrantItemAction gate (#2117)."""

    def setUp(self) -> None:
        self.target_character = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target_character)
        self.template = ItemTemplateFactory(name="Hand of the Betrayer")

    def _caller(self) -> object:
        caller = CharacterFactory()
        caller.msg = MagicMock()
        caller.search = MagicMock(return_value=self.target_character)
        return caller

    def test_junior_gm_succeeds(self) -> None:
        caller = self._caller()
        _make_gm(caller, GMLevel.JUNIOR)
        cmd = _build_cmd(caller, f"{self.target_character.key}=Hand of the Betrayer")
        cmd.func()

        assert ItemInstance.objects.filter(
            template=self.template, holder_character_sheet=self.target_sheet
        ).exists()

    def test_starting_gm_below_junior_tier_is_blocked(self) -> None:
        caller = self._caller()
        _make_gm(caller, GMLevel.STARTING)
        cmd = _build_cmd(caller, f"{self.target_character.key}=Hand of the Betrayer")
        cmd.func()

        caller.msg.assert_called_with("Requires Junior GM or higher.")
        assert not ItemInstance.objects.filter(holder_character_sheet=self.target_sheet).exists()

    def test_missing_gm_profile_is_blocked(self) -> None:
        caller = self._caller()
        caller.db_account = AccountFactory(is_staff=False)
        caller.save()
        cmd = _build_cmd(caller, f"{self.target_character.key}=Hand of the Betrayer")
        cmd.func()

        caller.msg.assert_called_with("GM trust required.")
        assert not ItemInstance.objects.filter(holder_character_sheet=self.target_sheet).exists()
