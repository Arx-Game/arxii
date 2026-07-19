"""Tests for CmdSeance (#2393)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from commands.seance import CmdSeance
from world.ceremonies.constants import CeremonyTypeKey, SeanceOfferStatus
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.services import open_ceremony
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipDeclaration


def _make_cmd(caller: MagicMock, account: object, args: str) -> CmdSeance:
    cmd = CmdSeance()
    cmd.caller = caller
    cmd.account = account
    cmd.args = args
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdSeanceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=officiant_sheet)
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)

        cls.dead_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=cls.dead_sheet,
            life_state=CharacterLifeState.DEAD,
            retired_at=timezone.now(),
        )
        cls.player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=cls.dead_sheet)
        RosterTenureFactory(roster_entry=entry, player_data=cls.player_data)
        cls.account = cls.player_data.account

        cls.ceremony = open_ceremony(
            officiant_persona=officiant_sheet.primary_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[cls.dead_sheet],
            location_profile=RoomProfileFactory(),
        )
        cls.offer = cls.ceremony.honorees.get(honoree_sheet=cls.dead_sheet).seance_offer

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

    def test_offers_subverb_same_as_bare(self) -> None:
        messages = self._run("offers")
        self.assertTrue(any(str(self.offer.pk) in m for m in messages))

    def test_no_offers_for_unrelated_account(self) -> None:
        from world.roster.factories import PlayerDataFactory

        stranger = PlayerDataFactory().account
        messages = self._run("", account=stranger)
        self.assertTrue(any("No seance is calling for you" in m for m in messages))

    def test_unknown_subverb_shows_usage(self) -> None:
        messages = self._run("banquet")
        self.assertTrue(any("Usage" in m for m in messages))

    def test_accept_missing_id_shows_usage(self) -> None:
        messages = self._run("accept")
        self.assertTrue(any("Usage" in m for m in messages))

    def test_accept_invalid_id(self) -> None:
        messages = self._run("accept notanumber")
        self.assertTrue(any("not a valid offer id" in m for m in messages))

    def test_accept_dispatches_action(self) -> None:
        messages = self._run(f"accept {self.offer.pk}")
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, SeanceOfferStatus.ACCEPTED)
        self.assertTrue(any("answer the seance" in m for m in messages))

    def test_decline_dispatches_action(self) -> None:
        messages = self._run(f"decline {self.offer.pk}")
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, SeanceOfferStatus.DECLINED)
        self.assertTrue(any("decline the seance" in m for m in messages))
