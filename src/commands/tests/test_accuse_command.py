"""Parse-layer tests for the ``/crime`` switch on ``CmdAccuse`` (#1825).

The criminal-accusation grammar (``accuse/crime <char> = <crime-kind> : <claim>``) is the
only genuinely new surface the heat-bridge wiring adds to the command. Its validation
branches raise ``CommandError`` before any target lookup, so they're testable without a
scene — the happy path is exercised end-to-end by the justice service tests.
"""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.social.accusations import CmdAccuse


def _cmd(args: str, switches: list[str]) -> CmdAccuse:
    cmd = CmdAccuse()
    cmd.args = args
    cmd.switches = switches
    return cmd


class CmdAccuseCrimeParseTests(TestCase):
    def test_crime_switch_requires_a_crime_kind_before_the_colon(self):
        # No ":" means no crime/claim split — a crime kind is mandatory with /crime.
        with self.assertRaises(CommandError):
            _cmd(" Bob = they stole it", ["crime"]).resolve_action_args()

    def test_crime_switch_requires_a_claim_after_the_colon(self):
        with self.assertRaises(CommandError):
            _cmd(" Bob = theft :", ["crime"]).resolve_action_args()

    def test_crime_switch_requires_a_target(self):
        with self.assertRaises(CommandError):
            _cmd(" = theft : they stole it", ["crime"]).resolve_action_args()

    def test_plain_accuse_still_requires_a_claim(self):
        with self.assertRaises(CommandError):
            _cmd(" Bob = ", []).resolve_action_args()
