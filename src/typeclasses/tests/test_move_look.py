"""The look a character gets on walking into a room is our look (#4329).

``DefaultCharacter.at_post_move`` sent a stock look over Evennia's ``desc``
Attribute, which nothing of ours writes: every room the builder made arrived as
"This is a room." with Evennia's contents list, while ``look`` in the same room
showed the authored description. The move now runs ``LookAction`` at the room, so
both come from the one renderer.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.eveditor import EvEditor

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.services.display import set_permanent_description
from typeclasses.mixins import ObjectParent
from world.character_sheets.factories import CharacterSheetFactory

ROOM = "typeclasses.rooms.Room"
EXIT = "typeclasses.exits.Exit"


def _look_frames(msg: MagicMock) -> list[str]:
    """The text of every frame typed ``look`` that ``msg`` received."""
    frames = []
    for call in msg.call_args_list:
        text = call.kwargs.get("text", call.args[0] if call.args else None)
        if isinstance(text, tuple) and text[1].get("type") == "look":
            frames.append(text[0])
    return frames


class MoveLookTests(TestCase):
    def setUp(self) -> None:
        self.origin = ObjectDBFactory(db_key="MoveLookOrigin", db_typeclass_path=ROOM)
        self.hall = ObjectDBFactory(db_key="MoveLookHall", db_typeclass_path=ROOM)
        set_permanent_description(self.hall, "A long hall of grey stone.")
        ObjectDBFactory(
            db_key="MoveLookDoor",
            db_typeclass_path=EXIT,
            location=self.hall,
            destination=self.origin,
        )
        self.mover = CharacterFactory(db_key="MoveLookMover", location=self.origin)
        # A played character always has an account; Evennia's command handler
        # reads the account's nicks before it runs any command.
        self.mover.db_account = AccountFactory(username="movelook_account")
        self.mover.save()
        CharacterSheetFactory(character=self.mover)
        # One window open: `has_account` counts sessions.
        self.mover.sessions.count = MagicMock(return_value=1)
        self.mover.msg = MagicMock()

    def test_walking_in_shows_the_authored_description_and_exits(self) -> None:
        self.mover.move_to(self.hall)

        looks = _look_frames(self.mover.msg)
        assert len(looks) == 1
        assert "A long hall of grey stone." in looks[0]
        assert "MoveLookDoor" in looks[0]
        assert "This is a room." not in looks[0]

    def test_the_look_goes_to_every_window(self) -> None:
        self.mover.move_to(self.hall)

        (call,) = [
            c
            for c in self.mover.msg.call_args_list
            if c.args and isinstance(c.args[0], tuple) and c.args[0][1].get("type") == "look"
        ]
        assert "session" not in call.kwargs

    def test_the_move_look_matches_typing_look(self) -> None:
        self.mover.move_to(self.hall)
        self.mover.execute_cmd("look")

        on_arrival, typed = _look_frames(self.mover.msg)
        assert on_arrival == typed

    def test_evennias_desc_attribute_is_not_what_arrives(self) -> None:
        self.hall.db.desc = "Stale text from the stock desc command."

        self.mover.move_to(self.hall)

        (look,) = _look_frames(self.mover.msg)
        assert "Stale text" not in look
        assert "A long hall of grey stone." in look

    def test_a_mover_in_the_line_editor_keeps_their_buffer(self) -> None:
        """The look is not typed: inside the editor, typed text joins the buffer."""
        EvEditor(self.mover, loadfunc=lambda _caller: "Half-written text.", key="movelook")

        self.mover.move_to(self.hall)

        assert self.mover.ndb._eveditor.get_buffer() == "Half-written text."
        assert len(_look_frames(self.mover.msg)) == 1

    def test_a_failing_look_still_lets_the_room_state_through(self) -> None:
        with (
            patch(
                "actions.definitions.perception.LookAction.execute",
                side_effect=RuntimeError("look broke"),
            ),
            patch.object(self.mover, "send_room_state") as room_state,
        ):
            self.mover.move_to(self.hall)

        room_state.assert_called_once_with()
        assert self.mover.location == self.hall
        assert _look_frames(self.mover.msg) == []

    def test_a_character_nobody_plays_gets_no_look(self) -> None:
        self.mover.sessions.count = MagicMock(return_value=0)

        self.mover.move_to(self.hall)

        assert _look_frames(self.mover.msg) == []

    def test_object_parent_has_no_post_move_hook_to_skip(self) -> None:
        """``super(DefaultCharacter, self)`` passes over ObjectParent too (#4329).

        Give ObjectParent an ``at_post_move`` and Character and CompanionObject would
        silently never run it; route their hooks through it before adding one.
        """
        assert "at_post_move" not in vars(ObjectParent)
