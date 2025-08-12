from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory


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

    def test_at_post_puppet_sends_commands(self):
        session1 = MagicMock()
        session2 = MagicMock()
        char = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        char.sessions.all = MagicMock(return_value=[session1, session2])
        with patch("typeclasses.characters.serialize_cmdset", return_value=["cmd"]):
            with patch("typeclasses.characters.DefaultCharacter.at_post_puppet"):
                char.at_post_puppet()
        session1.msg.assert_called_with(commands=(["cmd"], {}))
        session2.msg.assert_called_with(commands=(["cmd"], {}))

    def test_at_post_unpuppet_clears_commands(self):
        session = MagicMock()
        char = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        with patch("typeclasses.characters.DefaultCharacter.at_post_unpuppet"):
            char.at_post_unpuppet(session=session)
        session.msg.assert_called_with(commands=([], {}))
