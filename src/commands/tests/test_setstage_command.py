"""setstage command (#1498) — parse telnet text into SetTheStageAction kwargs."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.setstage import CmdSetStage
from world.areas.positioning.factories import PositionBlueprintFactory


class SetStageParseTests(TestCase):
    def _parse(self, args: str) -> dict:
        cmd = CmdSetStage()
        cmd.args = args
        return cmd.resolve_action_args()

    def test_name_resolves_to_blueprint_id(self) -> None:
        bp = PositionBlueprintFactory(name="The Dueling Green")
        assert self._parse("The Dueling Green") == {
            "blueprint_id": bp.pk,
            "replace": False,
        }

    def test_id_resolves_to_blueprint_id(self) -> None:
        bp = PositionBlueprintFactory(name="Tavern Booths")
        assert self._parse(str(bp.pk)) == {
            "blueprint_id": bp.pk,
            "replace": False,
        }

    def test_trailing_replace_sets_replace_true(self) -> None:
        bp = PositionBlueprintFactory(name="Court Dais")
        assert self._parse("Court Dais replace") == {
            "blueprint_id": bp.pk,
            "replace": True,
        }

    def test_missing_args_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._parse("")

    def test_unknown_name_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._parse("No Such Blueprint")
