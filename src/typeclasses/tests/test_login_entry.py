"""Login puppets the account's character; there is no OOC limbo (#3812).

``Account.at_post_login`` used to defer to Evennia's hook, which under
``AUTO_PUPPET_ON_LOGIN = False`` renders the stock OOC screen (``charcreate``,
``ic <name>`` ...) and waits for ``@ic``. Who a player is playing is decided
before they connect - the durable selection on the web, the last character on
telnet - so login resolves that and puppets it. ``@ic`` stays for switching.
"""

from __future__ import annotations

from unittest.mock import Mock, create_autospec, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from evennia.server.serversession import ServerSession

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.models import RosterType
from world.roster.services.selection import set_selected_entry


def _session() -> Mock:
    """A ServerSession-shaped mock: real signatures, no ``__iter__`` (typeclasses/CLAUDE.md)."""
    session = create_autospec(ServerSession, instance=True)
    session.puppet = None
    return session


def _texts(session: Mock) -> str:
    return "\n".join(str(call.args[0]) for call in session.msg.call_args_list if call.args)


class LoginEntryTestCase(TestCase):
    """Shared fixture: an account with two playable characters on the Active shelf."""

    def setUp(self) -> None:
        self.account = AccountFactory(typeclass="typeclasses.accounts.Account")
        self.roster = RosterFactory(name="Active", roster_type=RosterType.ACTIVE)
        self.entry_a, self.char_a = self._playable("Aria")
        self.entry_b, self.char_b = self._playable("Bianca")
        self.session = _session()
        self.account.sessions.all = lambda: [self.session]
        self.puppeted: list = []

        def record(_self, character, session):
            self.puppeted.append((character, session))
            return True, f"Now controlling {character.name}."

        patcher = patch.object(
            type(self.account), "puppet_character_in_session", autospec=True, side_effect=record
        )
        self.puppet_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def _playable(self, name: str):
        character = CharacterFactory(db_key=name)
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet, roster=self.roster)
        RosterTenureFactory(player_data=self.account.player_data, roster_entry=entry)
        return entry, character

    def _login(self) -> None:
        with patch("typeclasses.accounts.serialize_cmdset", return_value=["cmd"]):
            self.account.at_post_login(session=self.session)


class LoginResolvesTheCharacterTests(LoginEntryTestCase):
    def test_puppets_the_durable_selection(self) -> None:
        set_selected_entry(self.account.player_data, self.entry_b)

        self._login()

        self.assertEqual([c for c, _ in self.puppeted], [self.char_b])
        self.assertIs(self.puppeted[0][1], self.session)

    def test_falls_back_to_the_last_puppet_without_a_selection(self) -> None:
        self.account.db._last_puppet = self.char_b

        self._login()

        self.assertEqual([c for c, _ in self.puppeted], [self.char_b])

    def test_selection_outranks_the_last_puppet(self) -> None:
        set_selected_entry(self.account.player_data, self.entry_a)
        self.account.db._last_puppet = self.char_b

        self._login()

        self.assertEqual([c for c, _ in self.puppeted], [self.char_a])

    def test_a_selection_no_longer_playable_is_skipped(self) -> None:
        set_selected_entry(self.account.player_data, self.entry_b)
        closed_shelf = RosterFactory(
            name="Inactive", roster_type=RosterType.INACTIVE, is_active=False
        )
        self.entry_b.roster = closed_shelf
        self.entry_b.save()
        self.account.db._last_puppet = self.char_a

        self._login()

        self.assertEqual([c for c, _ in self.puppeted], [self.char_a])

    def test_a_sole_character_is_puppeted_with_no_selection_at_all(self) -> None:
        tenure = self.entry_b.tenures.get()
        tenure.end_date = timezone.now()
        tenure.save()  # a tenure save clears the account's and PlayerData's caches
        self.account.player_data.__dict__.pop("cached_tenures", None)
        self.assertEqual(self.account.get_available_characters(), [self.char_a])

        self._login()

        self.assertEqual([c for c, _ in self.puppeted], [self.char_a])

    def test_several_characters_and_no_selection_lists_them_and_puppets_nothing(self) -> None:
        self._login()

        self.assertEqual(self.puppeted, [])
        texts = _texts(self.session)
        self.assertIn("Aria", texts)
        self.assertIn("Bianca", texts)
        self.assertIn("@ic", texts)

    def test_no_characters_points_at_the_website(self) -> None:
        self.account.get_available_characters = list

        self._login()

        self.assertEqual(self.puppeted, [])
        self.assertIn(settings.FRONTEND_URL, _texts(self.session))


class LoginNeverShowsTheOOCScreenTests(LoginEntryTestCase):
    def test_no_stock_ooc_screen_and_no_ic_instruction(self) -> None:
        set_selected_entry(self.account.player_data, self.entry_a)

        with patch("typeclasses.accounts.DefaultAccount.at_look") as at_look:
            self._login()

        at_look.assert_not_called()
        texts = _texts(self.session)
        self.assertNotIn("charcreate", texts)
        self.assertNotIn("Use '@ic", texts)

    def test_keeps_evennias_login_side_effects(self) -> None:
        """Protocol flags, the ``logged_in`` OOB and the connect-channel line still happen."""
        self.account.attributes.add("_saved_protocol_flags", {"SCREENWIDTH": {0: 100}})
        set_selected_entry(self.account.player_data, self.entry_a)

        with patch.object(type(self.account), "_send_to_connect_channel") as announce:
            self._login()

        self.session.update_flags.assert_called_once_with(SCREENWIDTH={0: 100})
        self.session.msg.assert_any_call(logged_in={})
        self.session.msg.assert_any_call(commands=(["cmd"], {}))
        announce.assert_called_once()
        self.assertIn(self.account.key, announce.call_args.args[0])


class LoginHealsAnUnsetUpAccountTests(TestCase):
    def test_at_pre_login_restores_a_missing_cmdset(self) -> None:
        """The #3812 shape: typeclass right, cmdset storage empty, zero commands."""
        account = AccountFactory(typeclass="typeclasses.accounts.Account")
        account.db_cmdset_storage = None
        account.save(update_fields=["db_cmdset_storage"])
        account.cmdset.clear()
        account.cmdset.remove_default()

        account.at_pre_login()

        account.refresh_from_db()
        self.assertEqual(account.db_cmdset_storage, settings.CMDSET_ACCOUNT)
        account.cmdset.update()
        keys = {command.key for cmdset in account.cmdset.all() for command in cmdset.commands}
        self.assertIn("@ic", keys)

    def test_at_pre_login_leaves_a_healthy_account_alone(self) -> None:
        account = AccountFactory(typeclass="typeclasses.accounts.Account")
        with patch("typeclasses.accounts.heal_account_setup") as heal:
            heal.return_value = False
            account.at_pre_login()
        heal.assert_called_once_with(account)
