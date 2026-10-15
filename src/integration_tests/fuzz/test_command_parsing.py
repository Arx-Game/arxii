"""Fuzz: what a player can type never breaks the command layer (#3657).

The parsers every telnet command runs its input through (``split_switches``,
``parse_greedy_kwargs``) and the command handler itself are fed arbitrary
text. The properties are the contracts the commands rely on, not the
parsers' own output: a switch is lower-case and never empty, a key never
holds ``=``, the rest of the line survives, and an unknown line is answered,
never raised.
"""

from __future__ import annotations

import unittest

from hypothesis import assume, given, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from commands.command import parse_greedy_kwargs, split_switches
from integration_tests.harness import JourneyCase

printable_lines = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=80
)
letters = st.characters(whitelist_categories=("Ll", "Lu"))
lower = st.characters(whitelist_categories=("Ll",))
word = st.characters(whitelist_categories=("Ll", "Nd"))
typed = st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Po", "Zs"))


class SplitSwitchesHoldsItsContract(unittest.TestCase):
    @given(printable_lines)
    def test_never_raises_and_switches_are_clean(self, args: str) -> None:
        switches, rest = split_switches(args)
        for switch in switches:
            self.assertTrue(switch, "an empty switch")
            self.assertNotIn("/", switch)
            self.assertEqual(switch, switch.lower())
        self.assertIsInstance(rest, str)

    @given(printable_lines)
    def test_input_without_a_leading_slash_comes_back_unchanged(self, args: str) -> None:
        assume(not args.startswith("/"))
        self.assertEqual(split_switches(args), ([], args))

    @given(
        st.lists(st.text(alphabet=letters, min_size=1), min_size=1, max_size=4),
        printable_lines,
    )
    def test_typed_switches_are_recovered_in_order(self, switches: list[str], rest: str) -> None:
        line = "/" + "/".join(switches) + (" " + rest if rest else "")
        got, got_rest = split_switches(line)
        self.assertEqual(got, [s.lower() for s in switches])
        if rest:
            self.assertEqual(got_rest.strip(), rest.strip())


class ParseGreedyKwargsHoldsItsContract(unittest.TestCase):
    @given(printable_lines, st.one_of(st.none(), st.text(min_size=1, max_size=8)))
    def test_never_raises_and_keys_never_hold_equals(self, args: str, greedy: str | None) -> None:
        out = parse_greedy_kwargs(args, greedy_key=greedy)
        for key, value in out.items():
            self.assertNotIn("=", key)
            self.assertIsInstance(value, str)

    @given(
        st.text(alphabet=lower, min_size=1, max_size=6),
        st.text(alphabet=word, min_size=1, max_size=6),
        st.lists(st.text(alphabet=word, min_size=1, max_size=6), max_size=4),
    )
    def test_the_greedy_key_takes_the_rest_of_the_line(
        self, key: str, first: str, more: list[str]
    ) -> None:
        line = f"{key}={first} " + " ".join(more)
        out = parse_greedy_kwargs(line, greedy_key=key)
        self.assertEqual(out[key], " ".join([first, *more]).strip())


class UnknownLinesAreAnsweredNeverRaised(HypothesisTestCase, JourneyCase):
    """The handler's own contract: whatever is typed, the player hears back."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room()
        self.ysmay = self.make_player("Ysmay", room=self.room)

    @given(st.text(alphabet=typed, min_size=1, max_size=40))
    def test_a_line_that_matches_no_command_is_refused_with_a_reply(self, line: str) -> None:
        # No command key or alias starts with "zzqx", so the typed line can
        # match nothing: this is the handler's no-match path and only that.
        assume(line.strip())
        told = self.telnet(self.ysmay, "zzqx" + line)
        self.assertIn("is not available", told, f"{line!r} was not refused: {told!r}")
