"""``ooc <message>`` speaks out of character to the room (#4337).

Evennia's ``ooc`` unpuppeted the character into its stock account screen. The
ruling replaced it with Arx 1's: ``<OOC> Name says: text`` to everyone in the
room, so it never reads as the character talking.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.communication import OOC_USAGE, OOCSayAction
from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet
from commands.evennia_overrides.communication import CmdOOC
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import PlayerData
from typeclasses.characters import Character
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory, UnconsciousConditionFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import Mute
from world.scenes.mute_services import set_mute

OOC = {"type": "ooc"}
LINE = "I think we need a GM to rule on this."


def _played(name: str, room):
    """A character in ``room`` with a sheet and an account behind it."""
    character = CharacterFactory(db_key=name, location=room)
    character.db_account = AccountFactory(username=f"ooc_{name.lower()}")
    character.save()
    CharacterSheetFactory(character=character)
    return character


class OOCSayTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.speaker = _played("Apostate", self.room)
        self.listener = _played("Listener", self.room)

    def _say(self, text: str = LINE):
        """Run the action as the speaker; return (result, listener lines, speaker lines)."""
        with (
            patch.object(self.listener, "msg") as heard,
            patch.object(self.speaker, "msg") as echoed,
        ):
            result = OOCSayAction().run(self.speaker, text=text)
        return result, _texts(heard), _texts(echoed)

    def _listener_player(self) -> PlayerData:
        player, _ = PlayerData.objects.get_or_create(account=self.listener.account)
        return player

    def test_the_room_hears_an_ooc_line(self) -> None:
        result, heard, _echoed = self._say()

        assert result.success
        assert heard == [(f"<OOC> Apostate says: {LINE}", OOC)]

    def test_the_speaker_sees_their_own_line(self) -> None:
        _result, _heard, echoed = self._say()

        assert echoed == [(f"<OOC> You say: {LINE}", OOC)]

    def test_nothing_to_say_is_refused(self) -> None:
        result, heard, _echoed = self._say("   ")

        assert not result.success
        assert result.message == OOC_USAGE
        assert heard == []

    def test_a_listener_who_ooc_muted_the_speaker_hears_nothing(self) -> None:
        set_mute(
            owner=self._listener_player(),
            muted_persona=self.speaker.character_sheet.primary_persona,
            ic=False,
            ooc=True,
        )

        _result, heard, echoed = self._say()

        assert heard == []
        assert echoed == [(f"<OOC> You say: {LINE}", OOC)]

    def test_an_ic_only_mute_still_hears_ooc(self) -> None:
        set_mute(
            owner=self._listener_player(),
            muted_persona=self.speaker.character_sheet.primary_persona,
            ic=True,
            ooc=False,
        )

        _result, heard, _echoed = self._say()

        assert heard == [(f"<OOC> Apostate says: {LINE}", OOC)]

    def test_an_account_level_mute_hides_the_face_it_names(self) -> None:
        set_mute(
            owner=self._listener_player(),
            muted_persona=self.speaker.character_sheet.primary_persona,
            ic=False,
            ooc=True,
            account_level=True,
        )

        _result, heard, _echoed = self._say()

        assert heard == []

    def test_an_account_level_mute_does_not_follow_the_player_to_another_face(self) -> None:
        """The room would see the muter left out, and the silence would link the faces.

        An account-level mute names one face and snapshots the player behind it. The
        speaker now wears a different face; hiding that line from the muter alone would
        tell them who is under it (ADR-0204), so the line reaches them.
        """
        speaker_player, _ = PlayerData.objects.get_or_create(account=self.speaker.account)
        muted_face = PersonaFactory(character_sheet=self.speaker.character_sheet)
        Mute.objects.create(
            owner=self._listener_player(),
            muted_persona=muted_face,
            muted_player=speaker_player,
            account_level=True,
            mute_ic=False,
            mute_ooc=True,
        )

        _result, heard, _echoed = self._say()

        assert heard == [(f"<OOC> Apostate says: {LINE}", OOC)]

    def test_an_unconscious_occupant_does_not_hear_the_waking_room(self) -> None:
        """Dreamside perception (#2287) through the real exclusion registry, not a stub."""
        ConditionInstanceFactory(target=self.listener, condition=UnconsciousConditionFactory())

        _result, heard, _echoed = self._say()

        assert heard == []

    def test_each_listener_sees_their_own_name_for_the_speaker(self) -> None:
        """A mask shows the mask: the line asks the speaker for its name per listener."""
        with patch.object(
            Character,
            "get_display_name",
            side_effect=lambda looker=None, **_kwargs: f"a masked figure (to {looker.key})",
        ):
            _result, heard, _echoed = self._say()

        assert heard == [(f"<OOC> a masked figure (to Listener) says: {LINE}", OOC)]

    def test_braces_in_the_message_are_just_text(self) -> None:
        _result, heard, _echoed = self._say("{name} owes me {5} coins")

        assert heard == [("<OOC> Apostate says: {name} owes me {5} coins", OOC)]


class OOCCommandTests(TestCase):
    def test_the_character_cmdset_speaks_with_ooc(self) -> None:
        matches = [cmd for cmd in CharacterCmdSet().commands if cmd.key == "ooc"]

        assert len(matches) == 1
        assert isinstance(matches[0], CmdOOC)

    def test_evennias_unpuppeting_ooc_is_gone(self) -> None:
        """No account screen to fall into: login always puppets (ADR-0294)."""
        keys = {cmd.key for cmd in AccountCmdSet().commands}
        aliases = {alias for cmd in AccountCmdSet().commands for alias in cmd.aliases}

        assert "ooc" not in keys
        assert "unpuppet" not in aliases

    def test_the_command_hands_the_message_to_the_action(self) -> None:
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        speaker = _played("Speaker", room)
        cmd = CmdOOC()
        cmd.caller = speaker
        cmd.args = "  hello all  "

        assert cmd.resolve_action_args() == {"text": "hello all"}


def _texts(mock_msg) -> list:
    """The text payloads a patched ``msg`` received, positional or ``text=``."""
    payloads = []
    for call in mock_msg.call_args_list:
        if "text" in call.kwargs:
            payloads.append(call.kwargs["text"])
        elif call.args:
            payloads.append(call.args[0])
    return payloads
