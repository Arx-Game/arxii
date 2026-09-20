"""The web client's puppet handshake (#3933): a structured request, no text."""

from unittest.mock import MagicMock

from django.test import TestCase

from server.conf.inputfuncs import puppet


def _char(name: str) -> MagicMock:
    char = MagicMock()
    char.key = name
    return char


def _session(available, puppet_result=(True, "Now controlling Tehom.")) -> MagicMock:
    session = MagicMock()
    session.protocol_key = "websocket"
    session.account.get_available_characters.return_value = available
    session.account.puppet_character_in_session.return_value = puppet_result
    return session


class PuppetInputfuncTests(TestCase):
    def test_puppets_the_named_character_and_sends_no_text(self) -> None:
        tehom = _char("Tehom")
        session = _session([tehom])
        puppet(session, character="Tehom")
        session.account.puppet_character_in_session.assert_called_once_with(tehom, session)
        session.msg.assert_not_called()

    def test_matches_the_name_case_insensitively_and_trimmed(self) -> None:
        tehom = _char("Tehom")
        session = _session([tehom])
        puppet(session, character=" tehom ")
        session.account.puppet_character_in_session.assert_called_once_with(tehom, session)
        session.msg.assert_not_called()

    def test_a_refusal_is_a_command_error(self) -> None:
        session = _session([_char("Tehom")], puppet_result=(False, "That character is retired."))
        puppet(session, character="Tehom")
        session.msg.assert_called_once_with(
            command_error={"error": "That character is retired.", "command": "puppet"}
        )

    def test_an_unknown_name_is_a_command_error_and_never_puppets(self) -> None:
        session = _session([_char("Tehom")])
        puppet(session, character="Nobody")
        session.account.puppet_character_in_session.assert_not_called()
        session.msg.assert_called_once_with(
            command_error={"error": "Character 'Nobody' is not one of yours.", "command": "puppet"}
        )

    def test_a_missing_or_blank_or_non_string_name_is_a_command_error(self) -> None:
        for bad_value in (None, "", "  ", 42):
            session = _session([_char("Tehom")])
            if bad_value is None:
                puppet(session)
            else:
                puppet(session, character=bad_value)
            session.account.puppet_character_in_session.assert_not_called()
            session.msg.assert_called_once_with(
                command_error={"error": "Which character?", "command": "puppet"}
            )

    def test_a_session_without_an_account_is_a_command_error(self) -> None:
        session = _session([])
        session.account = None
        puppet(session, character="Tehom")
        session.msg.assert_called_once()
        session.account = None  # keep; puppet must not have been attempted
