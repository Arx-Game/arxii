"""The consent commands' registry and their pull-token parsing (#1337, #1919).

Every player path of the consent verbs (``intimidate <name>`` and its siblings opening a
request, ``accept``/``deny`` with and without an id, ``accept/<band>``, ``deny/blacklist``,
no scene, no target, no pending request) is typed through the command handler in
``integration_tests/test_faces_silences_and_the_floor_journeys.py``
(``PressingSomeoneInAScene``, #3657 tranche 9). What stays here has no player path: the
one-to-one map from social action keys to command classes, and the mixin that strips
``pull=`` tokens before a target name is resolved.
"""

from __future__ import annotations

from django.test import TestCase

from commands.consent import CmdIntimidate, CmdSeduce, ConsentRequestCommand


class AllSocialCommandsRegisteredTests(TestCase):
    """Every social-action singleton maps to a ConsentRequestCommand subclass."""

    def test_all_social_keys_have_commands(self) -> None:
        from commands.consent import (
            CmdDeceive,
            CmdEntrance,
            CmdFlirt,
            CmdPerform,
            CmdPersuade,
            CmdRestoreSense,
        )

        expected = {
            "intimidate": CmdIntimidate,
            "persuade": CmdPersuade,
            "deceive": CmdDeceive,
            "flirt": CmdFlirt,
            "seduce": CmdSeduce,
            "perform": CmdPerform,
            "entrance": CmdEntrance,
            "restore_sense": CmdRestoreSense,
        }
        for action_key, cls in expected.items():
            with self.subTest(action_key=action_key):
                self.assertEqual(cls.action_key, action_key)
                self.assertTrue(issubclass(cls, ConsentRequestCommand))

    def test_ritual_command_has_no_perform_alias(self) -> None:
        from commands.ritual import CmdRitual

        self.assertNotIn("perform", CmdRitual.aliases)


class PullParsingOnConsentCommandsTests(TestCase):
    """``ConsentRequestCommand`` parses ``pull=`` tokens via ``PullParsingMixin`` (#1919).

    Verifies that pull keywords are stripped from the raw args before
    target-name resolution, and that ``beseech=`` is discarded (combat-only).
    """

    def test_extract_pull_keywords_strips_tokens(self) -> None:
        from commands.pull_parsing import PullParsingMixin

        remainder, pull_val, resonance_val, tier, beseech = PullParsingMixin._extract_pull_keywords(
            "Bob pull=My Thread resonance=Fire tier=2"
        )
        self.assertEqual(remainder, "Bob")
        self.assertEqual(pull_val, "My Thread")
        self.assertEqual(resonance_val, "Fire")
        self.assertEqual(tier, 2)
        self.assertEqual(beseech, 0)

    def test_extract_pull_keywords_discards_beseech(self) -> None:
        from commands.pull_parsing import PullParsingMixin

        remainder, pull_val, _resonance, _tier, beseech = PullParsingMixin._extract_pull_keywords(
            "Bob pull=Thread resonance=Fire beseech=5"
        )
        self.assertEqual(remainder, "Bob")
        self.assertEqual(pull_val, "Thread")
        # beseech is extracted (so it doesn't contaminate the target name) but
        # will be discarded by ConsentRequestCommand (always passes beseech_bonus=0).
        self.assertEqual(beseech, 5)

    def test_extract_pull_keywords_no_pull_tokens(self) -> None:
        from commands.pull_parsing import PullParsingMixin

        remainder, pull_val, _resonance, _tier, _beseech = PullParsingMixin._extract_pull_keywords(
            "Bob"
        )
        self.assertEqual(remainder, "Bob")
        self.assertIsNone(pull_val)

    def test_consent_command_inherits_pull_parsing_mixin(self) -> None:
        from commands.consent import ConsentRequestCommand
        from commands.pull_parsing import PullParsingMixin

        self.assertTrue(issubclass(ConsentRequestCommand, PullParsingMixin))
