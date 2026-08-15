"""Tests for CmdConversion (#2361). Mirrors test_seance_command.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.conversion import CmdConversion
from world.ceremonies.constants import CeremonyTypeKey, ConversionOfferStatus
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.services import open_ceremony
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.factories import CharacterVitalsFactory
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipDeclaration


def _make_cmd(caller: MagicMock, account: object, args: str) -> CmdConversion:
    cmd = CmdConversion()
    cmd.caller = caller
    cmd.account = account
    cmd.args = args
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdConversionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        CeremonyTypeFactory(key=CeremonyTypeKey.CONVERSION, name="Conversion")
        officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=officiant_sheet)
        old_being = WorshippedBeingFactory()
        cls.new_being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=old_being)

        cls.convert_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=cls.convert_sheet)
        cls.player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=cls.convert_sheet)
        RosterTenureFactory(roster_entry=entry, player_data=cls.player_data)
        cls.account = cls.player_data.account

        cls.ceremony = open_ceremony(
            officiant_persona=officiant_sheet.primary_persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[cls.convert_sheet],
            location_profile=RoomProfileFactory(),
            being=cls.new_being,
        )
        cls.offer = cls.ceremony.honorees.get(honoree_sheet=cls.convert_sheet).conversion_offer

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str, account: object | None = None) -> list[str]:
        cmd = _make_cmd(self.caller, self.account if account is None else account, args)
        cmd.func()
        return _messages(self.caller)

    def test_bare_lists_pending_offer(self) -> None:
        messages = self._run("")
        self.assertTrue(any(str(self.offer.pk) in m for m in messages))
        self.assertTrue(any(self.new_being.name in m for m in messages))

    def test_offers_subverb_same_as_bare(self) -> None:
        messages = self._run("offers")
        self.assertTrue(any(str(self.offer.pk) in m for m in messages))

    def test_no_offers_for_unrelated_account(self) -> None:
        from world.roster.factories import PlayerDataFactory

        stranger = PlayerDataFactory().account
        messages = self._run("", account=stranger)
        self.assertTrue(any("No conversion rite is waiting" in m for m in messages))

    def test_unknown_subverb_shows_usage(self) -> None:
        messages = self._run("banquet")
        self.assertTrue(any("Usage" in m for m in messages))

    def test_accept_missing_id_shows_usage(self) -> None:
        messages = self._run("accept")
        self.assertTrue(any("Usage" in m for m in messages))

    def test_accept_invalid_id(self) -> None:
        messages = self._run("accept notanumber")
        self.assertTrue(any("not a valid offer id" in m for m in messages))

    def test_accept_dispatches_action_and_converts_sincerely(self) -> None:
        self._run(f"accept {self.offer.pk}")
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, ConversionOfferStatus.ACCEPTED)
        self.assertTrue(self.offer.is_sincere)

    def test_decline_dispatches_action(self) -> None:
        self._run(f"decline {self.offer.pk}")
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, ConversionOfferStatus.DECLINED)
