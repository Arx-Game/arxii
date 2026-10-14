"""The logout line is ours: typed, exclusion-routed, silent when sneaking (#4336).

Evennia's ``DefaultCharacter.at_post_unpuppet`` took the character off the grid
with an untyped "has left the game." to everyone in the room, dreamside
included. ``Character.at_post_unpuppet`` passes over it and ``_leave_the_grid``
does the same step with the line the login line already matched (#3933).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from typeclasses.characters import Character
from typeclasses.mixins import ObjectParent


class LogoutLineTests(TestCase):
    def setUp(self) -> None:
        # Fresh per test: the hook moves the leaver off the grid, and that change
        # would otherwise ride the identity map into the next test.
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.leaver = CharacterFactory(db_key="Leaver", location=self.room)
        self.listener = CharacterFactory(db_key="Listener", location=self.room)

    def _lines_heard(self, **unpuppet_kwargs) -> list:
        """Unpuppet the leaver's last window; return the text frames the listener got."""
        with (
            patch.object(self.listener, "msg") as heard,
            patch("world.scenes.friend_services.notify_friends_of_status"),
        ):
            self.leaver.at_post_unpuppet(**unpuppet_kwargs)
        return [call.kwargs["text"] for call in heard.call_args_list if "text" in call.kwargs]

    def test_the_room_hears_a_typed_departure(self) -> None:
        heard = self._lines_heard(session=MagicMock())

        assert heard == [("Leaver has left the game.", {"type": "move"})]

    def test_the_character_still_leaves_the_grid(self) -> None:
        self._lines_heard(session=MagicMock())

        assert self.leaver.location is None
        assert self.leaver.db.prelogout_location == self.room

    def test_a_lost_connection_keeps_its_reason(self) -> None:
        """Evennia's server sweep passes the reason (``evennia/server/service.py``)."""
        heard = self._lines_heard(reason=" (connection lost)")

        assert heard == [("Leaver has left the game (connection lost).", {"type": "move"})]

    def test_a_sneaking_character_logs_out_silently(self) -> None:
        with patch("world.stealth.services.is_sneaking", return_value=True):
            heard = self._lines_heard(session=MagicMock())

        assert heard == []
        assert self.leaver.location is None

    def test_a_dreamside_occupant_does_not_hear_it(self) -> None:
        with patch(
            "typeclasses.characters.resolve_broadcast_exclusions",
            return_value={self.listener},
        ):
            heard = self._lines_heard(session=MagicMock())

        assert heard == []

    def test_the_name_is_the_listeners_display_name(self) -> None:
        """A mask shows the mask: the line asks the leaver for its name per listener."""
        with patch.object(
            Character,
            "get_display_name",
            side_effect=lambda looker=None, **_kwargs: f"the masked figure (to {looker.key})",
        ):
            heard = self._lines_heard(session=MagicMock())

        assert heard == [
            ("the masked figure (to Listener) has left the game.", {"type": "move"}),
        ]

    def test_closing_one_of_two_windows_sends_nothing_and_stays(self) -> None:
        self.leaver.sessions.all = MagicMock(return_value=[MagicMock()])

        heard = self._lines_heard(session=MagicMock())

        assert heard == []
        assert self.leaver.location == self.room

    def test_object_parent_has_no_unpuppet_hook_to_skip(self) -> None:
        """``super(DefaultCharacter, self)`` passes over ObjectParent too (#4336).

        Give ObjectParent an ``at_post_unpuppet`` and Character would skip it.
        """
        assert "at_post_unpuppet" not in vars(ObjectParent)
