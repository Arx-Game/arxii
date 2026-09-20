"""Puppet hooks fire per character, not per window (#3812).

With sessions sharing a character (``MULTISESSION_MODE = 3``), a second tab
opening is not the character coming online and the first tab closing is not
the character going offline. The friends alert and the offline story catch-up
fire when the FIRST session arrives; the offline alert and the presence-buff
clear fire when the LAST session leaves. The joining window gets its own
``look`` and room state rather than spraying them into every other window.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import ObjectDBFactory

CHARACTER = "typeclasses.characters.Character"


class FirstSessionArrivesTests(TestCase):
    def _puppet_with(self, sessions):
        char = ObjectDBFactory(db_typeclass_path=CHARACTER)
        char.sessions.all = MagicMock(return_value=sessions)
        char.msg = MagicMock()
        char.send_room_state = MagicMock()
        char.execute_cmd = MagicMock()
        with (
            patch("typeclasses.characters.serialize_cmdset", return_value=["cmd"]),
            patch.object(ObjectDB, "location", new_callable=PropertyMock, return_value=MagicMock()),
            patch("world.scenes.friend_services.notify_friends_of_status") as friends,
            patch("world.stories.services.login.catch_up_character_stories") as catch_up,
        ):
            char.at_post_puppet()
        return char, friends, catch_up

    def test_first_session_announces_online_and_catches_up(self) -> None:
        only = MagicMock()

        char, friends, catch_up = self._puppet_with([only])

        friends.assert_called_once_with(char, online=True)
        catch_up.assert_called_once_with(char)

    def test_second_session_is_silent_for_friends_and_stories(self) -> None:
        first, second = MagicMock(), MagicMock()

        _char, friends, catch_up = self._puppet_with([first, second])

        friends.assert_not_called()
        catch_up.assert_not_called()

    def test_the_joining_window_gets_its_own_look_and_room_state(self) -> None:
        first, second = MagicMock(), MagicMock()

        char, _friends, _catch_up = self._puppet_with([first, second])

        char.send_room_state.assert_called_once_with(session=second)
        char.execute_cmd.assert_called_once_with("look", session=second)
        first.msg.assert_called_with(commands=(["cmd"], {}))
        second.msg.assert_called_with(commands=(["cmd"], {}))


class LastSessionLeavesTests(TestCase):
    def _unpuppet_with(self, remaining, leaving):
        char = ObjectDBFactory(db_typeclass_path=CHARACTER)
        char.sessions.all = MagicMock(return_value=remaining)
        with (
            patch("typeclasses.characters.DefaultCharacter.at_post_unpuppet"),
            patch("world.scenes.friend_services.notify_friends_of_status") as friends,
            patch("typeclasses.characters.clear_resonance_alignment") as clear,
        ):
            char.at_post_unpuppet(session=leaving)
        return char, friends, clear

    def test_closing_one_of_two_windows_is_not_going_offline(self) -> None:
        staying, leaving = MagicMock(), MagicMock()

        _char, friends, clear = self._unpuppet_with([staying], leaving)

        friends.assert_not_called()
        clear.assert_not_called()
        leaving.msg.assert_called_with(commands=([], {}))
        staying.msg.assert_not_called()

    def test_closing_the_last_window_announces_offline(self) -> None:
        leaving = MagicMock()

        char, friends, _clear = self._unpuppet_with([], leaving)

        friends.assert_called_once_with(char, online=False)


class LifecycleOutputTests(TestCase):
    """Evennia's stock post-puppet output, retyped for the web feed (#3933).

    ``at_post_puppet`` no longer calls the base hook (it sent an untaggable
    ``You become`` line, a stock look over the Evennia ``desc`` attribute, and
    an untyped room broadcast); ``_announce_puppet`` sends the same
    information tagged ``lifecycle``/``arrive``, and the joining session's own
    look runs with ``on_entry`` set so a client showing the room can drop it.
    """

    def _puppet(self):
        char = ObjectDBFactory(db_typeclass_path=CHARACTER)
        joining = MagicMock()
        char.sessions.all = MagicMock(return_value=[joining])
        char.msg = MagicMock()
        char.send_room_state = MagicMock()
        seen_options = []

        def fake_look(cmd, session=None):
            seen_options.append(session.ndb.text_frame_options)

        char.execute_cmd = MagicMock(side_effect=fake_look)
        room = MagicMock()
        with (
            patch("typeclasses.characters.serialize_cmdset", return_value=["cmd"]),
            patch.object(ObjectDB, "location", new_callable=PropertyMock, return_value=room),
            patch("world.scenes.friend_services.notify_friends_of_status"),
            patch("world.stories.services.login.catch_up_character_stories"),
        ):
            char.at_post_puppet()
        return char, joining, room, seen_options

    def test_you_become_is_a_lifecycle_frame_and_the_stock_look_is_gone(self) -> None:
        char, _joining, _room, _seen_options = self._puppet()

        expected = (
            f"You become {char.key}.",
            {"type": "lifecycle", "event": "become"},
        )
        assert expected in [call.args[0] for call in char.msg.call_args_list]
        assert not any(
            isinstance(call.args[0], tuple) and call.args[0][1].get("type") == "look"
            for call in char.msg.call_args_list
        )

    def test_the_entry_look_runs_under_the_on_entry_option_and_clears_it(self) -> None:
        char, joining, _room, seen_options = self._puppet()

        char.execute_cmd.assert_called_once_with("look", session=joining)
        assert seen_options == [{"on_entry": True}]
        assert joining.ndb.text_frame_options is None

    def test_the_room_hears_a_typed_arrival(self) -> None:
        char, _joining, room, _seen_options = self._puppet()

        room.msg_contents.assert_called_once()
        args, kwargs = room.msg_contents.call_args
        text, options = args[0]
        assert options == {"type": "arrive"}
        assert "has entered the game" in text
        assert kwargs["exclude"] == [char]
        assert kwargs["mapping"] == {"name": char}
