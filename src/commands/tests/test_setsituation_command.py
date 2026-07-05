"""setsituation command (#1895) — parse telnet text into SetSituationAction kwargs."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.setsituation import CmdSetSituation
from world.mechanics.factories import SituationTemplateFactory


class SetSituationParseTests(TestCase):
    def _parse(self, args: str) -> dict:
        cmd = CmdSetSituation()
        cmd.args = args
        return cmd.resolve_action_args()

    def test_name_resolves_to_template_id(self) -> None:
        template = SituationTemplateFactory(name="The Sealed Passage")
        assert self._parse("The Sealed Passage") == {
            "situation_template_id": template.pk,
        }

    def test_id_resolves_to_template_id(self) -> None:
        template = SituationTemplateFactory(name="Ambush Point")
        assert self._parse(str(template.pk)) == {
            "situation_template_id": template.pk,
        }

    def test_missing_args_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._parse("")

    def test_unknown_name_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._parse("No Such Situation")
