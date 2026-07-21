"""Tests for CmdGrantDistinction (#2037), gated on JUNIOR-tier GM trust or staff.

Mirrors ``test_grant_item.py``: the caller is a real ``CharacterFactory``
instance with ``search``/``msg`` monkey-patched onto the instance, and the
target is a real character so ``target.sheet_data`` resolves for real.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.grant_distinction import CmdGrantDistinction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _build_cmd(caller, args: str = "") -> CmdGrantDistinction:
    cmd = CmdGrantDistinction()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"grant_distinction {args}".strip()
    return cmd


def _make_gm(character, level: str) -> None:
    """Attach a live roster tenure + GMProfile at ``level`` to ``character``."""
    CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet__character=character)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    GMProfileFactory(account=tenure.player_data.account, level=level)


class CmdGrantDistinctionTests(TestCase):
    def setUp(self) -> None:
        self.staff_character = CharacterFactory()
        self.staff_character.msg = MagicMock()
        self.staff_character.search = MagicMock()
        self.staff_character.db_account = AccountFactory(is_staff=True)
        self.staff_character.save()
        self.target_character = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target_character)
        self.distinction = DistinctionFactory(
            name="Silver Tongue", slug="silver-tongue", max_rank=3
        )
        self.staff_character.search.return_value = self.target_character

    def test_grants_distinction_to_target_character(self) -> None:
        cmd = _build_cmd(
            self.staff_character,
            f"{self.target_character.key}=silver-tongue",
        )
        cmd.func()

        cd = CharacterDistinction.objects.get(
            character=self.target_character.sheet_data, distinction=self.distinction
        )
        assert cd.rank == 1
        assert cd.origin == DistinctionOrigin.GM_AWARD
        self.staff_character.msg.assert_called_with(
            f"Awarded 'Silver Tongue' (rank 1) to {self.target_character.key}."
        )

    def test_rank_suffix_sets_explicit_rank(self) -> None:
        cmd = _build_cmd(
            self.staff_character,
            f"{self.target_character.key}=silver-tongue,3",
        )
        cmd.func()

        cd = CharacterDistinction.objects.get(
            character=self.target_character.sheet_data, distinction=self.distinction
        )
        assert cd.rank == 3
        self.staff_character.msg.assert_called_with(
            f"Awarded 'Silver Tongue' (rank 3) to {self.target_character.key}."
        )

    def test_garbage_rank_reports_error(self) -> None:
        cmd = _build_cmd(
            self.staff_character,
            f"{self.target_character.key}=silver-tongue,lots",
        )
        cmd.func()

        self.staff_character.msg.assert_any_call("rank must be a whole number.")
        assert not CharacterDistinction.objects.filter(
            character=self.target_character.sheet_data
        ).exists()

    def test_unknown_slug_reports_error(self) -> None:
        cmd = _build_cmd(
            self.staff_character,
            f"{self.target_character.key}=no-such-distinction",
        )
        cmd.func()

        self.staff_character.msg.assert_called()
        assert not CharacterDistinction.objects.filter(
            character=self.target_character.sheet_data
        ).exists()

    def test_missing_equals_reports_usage(self) -> None:
        cmd = _build_cmd(self.staff_character, "justaname")
        cmd.func()

        self.staff_character.msg.assert_any_call(
            "Usage: grant_distinction <character>=<distinction slug>[,rank]"
        )

    def test_search_none_does_not_message_twice(self) -> None:
        self.staff_character.search.return_value = None
        cmd = _build_cmd(self.staff_character, "Nobody=silver-tongue")
        cmd.func()

        self.staff_character.msg.assert_not_called()


class CmdGrantDistinctionGMTrustTests(TestCase):
    """Trust-tier journeys for the JUNIOR-tier GMAwardDistinctionAction gate."""

    def setUp(self) -> None:
        self.target_character = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target_character)
        self.distinction = DistinctionFactory(
            name="Silver Tongue", slug="silver-tongue", max_rank=3
        )

    def _caller(self) -> object:
        caller = CharacterFactory()
        caller.msg = MagicMock()
        caller.search = MagicMock(return_value=self.target_character)
        return caller

    def test_junior_gm_succeeds(self) -> None:
        caller = self._caller()
        _make_gm(caller, GMLevel.JUNIOR)
        cmd = _build_cmd(caller, f"{self.target_character.key}=silver-tongue")
        cmd.func()

        assert CharacterDistinction.objects.filter(
            character=self.target_character.sheet_data, distinction=self.distinction
        ).exists()

    def test_starting_gm_below_junior_tier_is_blocked(self) -> None:
        caller = self._caller()
        _make_gm(caller, GMLevel.STARTING)
        cmd = _build_cmd(caller, f"{self.target_character.key}=silver-tongue")
        cmd.func()

        caller.msg.assert_called_with("Requires Junior GM or higher.")
        assert not CharacterDistinction.objects.filter(
            character=self.target_character.sheet_data
        ).exists()

    def test_missing_gm_profile_is_blocked(self) -> None:
        caller = self._caller()
        caller.db_account = AccountFactory(is_staff=False)
        caller.save()
        cmd = _build_cmd(caller, f"{self.target_character.key}=silver-tongue")
        cmd.func()

        caller.msg.assert_called_with("GM trust required.")
        assert not CharacterDistinction.objects.filter(
            character=self.target_character.sheet_data
        ).exists()
