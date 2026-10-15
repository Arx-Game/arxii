"""The harness proves itself on the smallest journeys (#3657).

These pin what ``JourneyCase`` promises: a typed line reaches the real command
handler (an unknown command is refused the way a player sees it; a switch
reaches ``parse``), the room hears what a player says, the web seam runs the
same action, and a command's own exception surfaces instead of being logged.
"""

from __future__ import annotations

from evennia import CmdSet

from commands.command import ArxCommand
from integration_tests.harness import JourneyCase


def _one_command_set(command_class: type[ArxCommand]) -> type[CmdSet]:
    """A cmdset holding one command, the way a test adds a probe to a character."""

    class OneCommandSet(CmdSet):
        key = f"probe_{command_class.key}"

        def at_cmdset_creation(self) -> None:
            self.add(command_class())

    return OneCommandSet


class SpeechReachesTheRoom(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.watch(self.hobb)

    def test_a_greeting_is_heard_by_the_speaker_and_the_room(self) -> None:
        told = self.telnet(self.ysmay, "say Good evening.")
        self.assertIn('You say "Good evening."', told)
        self.assertTold(self.hobb, 'Ysmay says "Good evening."')
        self.assertNotTold(self.hobb, "You say")

    def test_telnet_returns_only_this_command_and_said_keeps_the_rest(self) -> None:
        first = self.telnet(self.ysmay, "say One.")
        second = self.telnet(self.ysmay, "say Two.")
        self.assertIn("One.", first)
        self.assertNotIn("One.", second)
        self.assertIn("Two.", second)
        self.assertIn("One.", self.said(self.ysmay))

    def test_an_unknown_command_is_refused_as_a_player_sees_it(self) -> None:
        told = self.telnet(self.ysmay, "xyzzy")
        self.assertIn("xyzzy", told)
        self.assertNotTold(self.hobb, "xyzzy")

    def test_look_names_the_room(self) -> None:
        self.assertIn("The Lantern", self.telnet(self.ysmay, "look"))


class TheHandlerIsOnThePath(JourneyCase):
    """What the old ``cmd.func()`` tests skipped: ``parse`` and cmdset membership."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room()
        self.ysmay = self.make_player("Ysmay", room=self.room)

    def test_a_switch_reaches_the_command_through_parse(self) -> None:
        seen: dict[str, object] = {}

        class CmdProbe(ArxCommand):
            key = "probe"
            takes_switches = True

            def func(self) -> None:
                seen["switches"] = list(self.switches)
                seen["args"] = self.args
                self.msg(f"probe saw {self.switches} and {self.args!r}")

        self.ysmay.cmdset.add(_one_command_set(CmdProbe))
        told = self.telnet(self.ysmay, "probe/finish Heron Plate")
        self.assertEqual(seen["switches"], ["finish"])
        self.assertEqual(seen["args"], " Heron Plate")
        self.assertIn("probe saw", told)

    def test_a_command_that_raises_fails_the_test_instead_of_logging(self) -> None:
        class CmdBroken(ArxCommand):
            key = "broken"

            def func(self) -> None:
                msg = "the seam broke"
                raise RuntimeError(msg)

        self.ysmay.cmdset.add(_one_command_set(CmdBroken))
        with self.assertRaisesRegex(RuntimeError, "the seam broke"):
            self.telnet(self.ysmay, "broken")


class TheWebSeamRunsTheSameAction(JourneyCase):
    def test_look_through_dispatch_matches_the_typed_look(self) -> None:
        room = self.make_room("The Lantern")
        ysmay = self.make_player("Ysmay", room=room)
        result = self.web(ysmay, "look", target=room)
        self.assertFalse(result.deferred)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("The Lantern", result.detail.message)
        self.assertIn("The Lantern", self.telnet(ysmay, "look"))

    def test_the_api_client_is_signed_in_as_the_player(self) -> None:
        room = self.make_room()
        ysmay = self.make_player("Ysmay", room=room)
        response = self.api(self.account_of(ysmay)).get("/api/user/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.account_of(ysmay).pk)
