"""Telnet: a stewarded being's table GM answers a closed pledge (#4333 slice 4).

``gm prompts`` names the being's answer; ``gm prompt answer <id>`` lists what the
steward can send; ``answer=`` and ``text=`` send it; ``gm prompt dismiss`` draws
an authored answer. Rows are seeded by the slice's own fixture.
"""

from unittest import mock

from commands.gm_ops import CmdGMDashboard
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptStatus
from world.gm.models import GMPrompt
from world.worship.models import Vision
from world.worship.tests.test_stewards import StewardTestBase


class GMBeingAnswerTelnetTests(StewardTestBase):
    def setUp(self) -> None:
        self.gm_char = CharacterSheetFactory().character
        self.gm_char.account = self.gm_account

    def _run(self, args: str) -> str:
        cmd = CmdGMDashboard()
        cmd.caller = self.gm_char
        cmd.account = self.gm_account
        cmd.args = args
        cmd.switches = []
        cmd.cmdname = CmdGMDashboard.key
        cmd.raw_string = f"gm {args}"
        cmd.msg = mock.Mock()
        cmd.func()
        return "\n".join(str(c.args[0]) for c in cmd.msg.call_args_list)

    def test_listing_then_sending_an_authored_answer(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")

        listed = self._run("prompts")
        self.assertIn(f"[{prompt.pk}] Being answer", listed)
        self.assertIn("Ombrin answers", listed)
        self.assertIn(f"gm prompt answer {prompt.pk}", listed)

        options = self._run(f"prompt answer {prompt.pk}")
        self.assertIn(f"answer={answer.pk} (Success)", options)
        self.assertIn("text=<your words> is allowed.", options)
        self.assertIn(f"clue={self.fact_clue.pk}", options)

        sent = self._run(f"prompt answer {prompt.pk} answer={answer.pk}")
        self.assertEqual(sent, "Sent as a vision from Ombrin.")
        self.assertEqual(Vision.objects.get(recipient=self.sheet).answer, answer)

    def test_sending_your_own_words(self) -> None:
        self._full_answer("Success")
        prompt = self._closed("Success")

        sent = self._run(f"prompt answer {prompt.pk} text=[GM-written free text]")

        self.assertEqual(sent, "Sent as a vision from Ombrin.")
        self.assertEqual(Vision.objects.get(recipient=self.sheet).body, "[GM-written free text]")

    def test_dismissing_draws_an_authored_answer(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")

        self._run(f"prompt dismiss {prompt.pk}")

        self.assertEqual(GMPrompt.objects.get(pk=prompt.pk).status, GMPromptStatus.DISMISSED)
        self.assertEqual(Vision.objects.get(recipient=self.sheet).answer, answer)
