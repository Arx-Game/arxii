"""Movement announcements are typed for the web feed (#3856).

Evennia types both broadcasts ``move``: the departure the old room hears and the
arrival the new room hears. The client shows them differently (someone arriving
is something to act on; someone leaving is not), so our ``announce_move_to``
retypes the arrival ``arrive``. The stealth arrival line, an identity-free
"unseen presence" echo that replaces the normal announce, is an arrival too.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory

ROOM = "typeclasses.rooms.Room"


def _typed_text_frames(msg: MagicMock) -> list[tuple[str, dict]]:
    """The ``(text, options)`` tuples a bystander's ``msg`` received."""
    frames = []
    for call in msg.call_args_list:
        text = call.kwargs.get("text", call.args[0] if call.args else None)
        if isinstance(text, tuple):
            frames.append(text)
    return frames


class MoveAnnouncementKindTests(TestCase):
    def setUp(self) -> None:
        self.origin = ObjectDBFactory(db_key="Origin", db_typeclass_path=ROOM)
        self.destination = ObjectDBFactory(db_key="Destination", db_typeclass_path=ROOM)
        self.mover = CharacterFactory(location=self.origin)
        self.stayer = CharacterFactory(location=self.origin)
        self.greeter = CharacterFactory(location=self.destination)
        self.stayer.msg = MagicMock()
        self.greeter.msg = MagicMock()

    def test_the_new_room_hears_an_arrival_and_the_old_room_a_move(self) -> None:
        self.mover.move_to(self.destination)

        arrival = _typed_text_frames(self.greeter.msg)
        departure = _typed_text_frames(self.stayer.msg)
        self.assertEqual([options for _, options in arrival], [{"type": "arrive"}])
        self.assertEqual([options for _, options in departure], [{"type": "move"}])

    def test_a_stealthy_arrival_is_still_typed_arrive(self) -> None:
        with (
            patch("world.stealth.services.reroll_on_arrival", return_value=True),
            patch("world.stealth.services.is_sneaking", return_value=True),
        ):
            self.mover.move_to(self.destination)

        arrival = _typed_text_frames(self.greeter.msg)
        self.assertEqual(len(arrival), 1)
        text, options = arrival[0]
        self.assertIn("unseen presence", text)
        self.assertEqual(options, {"type": "arrive"})
        # A sneaking departure says nothing at all (#3288), typed or otherwise.
        self.stayer.msg.assert_not_called()
