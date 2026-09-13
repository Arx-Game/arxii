from unittest.mock import MagicMock, create_autospec, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.roster.models import Roster, RosterEntry, RosterType


class CommandUpdateTests(TestCase):
    def test_at_post_login_sends_commands(self):
        session = MagicMock()
        account = AccountFactory(typeclass="typeclasses.accounts.Account")
        account.sessions.all = MagicMock(return_value=[session])
        account.get_available_characters = MagicMock(return_value=[])
        with patch("typeclasses.accounts.serialize_cmdset", return_value=["cmd"]):
            with patch("typeclasses.accounts.DefaultAccount.at_post_login"):
                account.at_post_login(session=session)
        session.msg.assert_any_call(commands=(["cmd"], {}))

    def test_at_post_login_characterless_message_points_to_web(self):
        """#2122 — the no-characters login message signposts the web app."""
        session = MagicMock()
        account = AccountFactory(typeclass="typeclasses.accounts.Account")
        account.sessions.all = MagicMock(return_value=[session])
        account.get_available_characters = MagicMock(return_value=[])
        with patch("typeclasses.accounts.serialize_cmdset", return_value=["cmd"]):
            with patch("typeclasses.accounts.DefaultAccount.at_post_login"):
                account.at_post_login(session=session)

        texts = [str(call.args[0]) for call in session.msg.call_args_list if call.args]
        combined = "\n".join(texts)
        self.assertIn(settings.FRONTEND_URL, combined)
        self.assertIn("no available characters", combined.lower())

    def test_at_post_login_completes_against_a_real_session_signature(self):
        """The session is a ServerSession, and its hooks must be called as such.

        Every other test in this class passes a bare ``MagicMock`` as the
        session, which answers any attribute with any arity - so
        ``session.at_login()`` succeeded here while raising
        ``TypeError: ServerSession.at_login() missing 1 required positional
        argument: 'account'`` on every real login in production, taking the
        cmdset payload and the character list down with it (digest #3736).
        ``create_autospec`` is the difference: it enforces Evennia's real
        signatures, so a call this method cannot legally make fails the test.
        """
        from evennia.server.serversession import ServerSession

        session = create_autospec(ServerSession, instance=True)
        account = AccountFactory(typeclass="typeclasses.accounts.Account")
        account.sessions.all = MagicMock(return_value=[session])
        account.get_available_characters = MagicMock(return_value=[])

        with patch("typeclasses.accounts.serialize_cmdset", return_value=["cmd"]):
            with patch("typeclasses.accounts.DefaultAccount.at_post_login"):
                account.at_post_login(session=session)

        session.msg.assert_any_call(commands=(["cmd"], {}))

    def test_at_post_login_leaves_portal_side_autologin_to_evennia(self):
        """Never call the Portal's ``at_login()`` from this Server-side hook.

        ``sessionhandler.login()`` sends the SLOGIN AMP op before invoking this
        hook, and the Portal answers it in ``server_logged_in()`` by calling its
        own ``session.at_login()`` - the no-argument
        ``SecureWebSocketClient.at_login`` that stores the autologin uid and
        nonce. Reaching for that name from the Server hits ``ServerSession``'s
        two-argument hook of the same name instead.
        """
        from evennia.server.serversession import ServerSession

        session = create_autospec(ServerSession, instance=True)
        account = AccountFactory(typeclass="typeclasses.accounts.Account")
        account.sessions.all = MagicMock(return_value=[session])
        account.get_available_characters = MagicMock(return_value=[])

        with patch("typeclasses.accounts.serialize_cmdset", return_value=["cmd"]):
            with patch("typeclasses.accounts.DefaultAccount.at_post_login"):
                account.at_post_login(session=session)

        session.at_login.assert_not_called()

    def test_at_post_puppet_sends_commands(self):
        session1 = MagicMock()
        session2 = MagicMock()
        char = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        char.sessions.all = MagicMock(return_value=[session1, session2])
        char.send_room_state = MagicMock()
        with patch("typeclasses.characters.serialize_cmdset", return_value=["cmd"]):
            with patch("typeclasses.characters.DefaultCharacter.at_post_puppet"):
                char.at_post_puppet()
        session1.msg.assert_called_with(commands=(["cmd"], {}))
        session2.msg.assert_called_with(commands=(["cmd"], {}))
        # The newest session (last in sessions.all()) is the one that just
        # joined; only it gets the room state (#3812).
        char.send_room_state.assert_called_once_with(session=session2)

    def test_at_post_unpuppet_clears_commands(self):
        session = MagicMock()
        char = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        with patch("typeclasses.characters.DefaultCharacter.at_post_unpuppet"):
            char.at_post_unpuppet(session=session)
        session.msg.assert_called_with(commands=([], {}))

    def test_at_post_puppet_updates_last_puppeted(self):
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        char = CharacterFactory(location=room)
        roster = Roster.objects.create(name="Active", roster_type=RosterType.ACTIVE)
        from world.character_sheets.models import CharacterSheet

        sheet, _ = CharacterSheet.objects.get_or_create(character=char)
        entry = RosterEntry.objects.create(character_sheet=sheet, roster=roster)
        now = timezone.now()
        with (
            patch("typeclasses.characters.serialize_cmdset", return_value=["cmd"]),
            patch("typeclasses.characters.timezone.now", return_value=now),
        ):
            char.at_post_puppet()
        entry.refresh_from_db()
        assert entry.last_puppeted == now


class GetSeanceManifestableCharactersTests(TestCase):
    """PlayerData.get_seance_manifestable_characters (#2393)."""

    def test_excludes_alive_and_non_retired_dead(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.vitals.factories import CharacterVitalsFactory

        player_data = PlayerDataFactory()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)  # ALIVE
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)

        self.assertEqual(player_data.get_seance_manifestable_characters(), [])

    def test_includes_retired_with_accepted_open_offer(self) -> None:
        from django.utils import timezone

        from evennia_extensions.factories import RoomProfileFactory
        from world.ceremonies.constants import CeremonyTypeKey
        from world.ceremonies.factories import CeremonyTypeFactory
        from world.ceremonies.services import open_ceremony, respond_to_seance_offer
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.vitals.constants import CharacterLifeState
        from world.vitals.factories import CharacterVitalsFactory
        from world.worship.factories import WorshippedBeingFactory
        from world.worship.models import WorshipDeclaration

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        player_data = PlayerDataFactory()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=sheet, life_state=CharacterLifeState.DEAD, retired_at=timezone.now()
        )
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)

        officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=officiant_sheet)

        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)
        ceremony = open_ceremony(
            officiant_persona=officiant_sheet.primary_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[sheet],
            location_profile=RoomProfileFactory(),
        )
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer
        respond_to_seance_offer(offer, account=player_data.account, accept=True)

        self.assertEqual(player_data.get_seance_manifestable_characters(), [sheet.character])
