"""setstage command (#1498) — parse telnet text into SetTheStageAction kwargs."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.setstage import CmdSetStage
from evennia_extensions.factories import AccountFactory
from world.areas.positioning.factories import PositionBlueprintFactory
from world.areas.positioning.models import Position


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


def _make_staff_character(key: str, room) -> object:
    """Return an Evennia character connected to a staff account."""
    from evennia import create_object

    char = create_object("typeclasses.characters.Character", key=key, location=room, nohome=True)
    account = AccountFactory(username=f"account_{key}", is_staff=True)
    account.save()
    char.db_account = account
    char.save()
    return char


def _make_room(key: str = "The Solar") -> object:
    from evennia import create_object

    return create_object("typeclasses.rooms.Room", key=key, nohome=True)


class SetStageHubTests(TestCase):
    def _run(self, args: str, caller) -> list[str]:
        cmd = CmdSetStage()
        cmd.args = args
        cmd.caller = caller
        messages: list[str] = []
        caller.msg = lambda *a, **_k: messages.append(a[0] if a else "")
        cmd.func()
        return messages

    def test_bare_setstage_shows_hub(self) -> None:
        room = _make_room()
        caller = _make_staff_character("stagehand", room)
        msgs = self._run("", caller)
        assert any("No positions" in m or "positions" in m.lower() for m in msgs)

    def test_list_lists_blueprints(self) -> None:
        PositionBlueprintFactory(name="Alpha")
        PositionBlueprintFactory(name="Beta")
        caller = _make_staff_character("listonly", _make_room())
        msgs = self._run("list", caller)
        assert any("Alpha" in m for m in msgs)
        assert any("Beta" in m for m in msgs)


class SetStageRunTests(TestCase):
    def test_setstage_name_instantiates_positions(self) -> None:
        room = _make_room()
        caller = _make_staff_character("stager", room)
        # A blueprint with one position template -> one live Position in the room.
        bp = PositionBlueprintFactory(name="Lone Dais")
        from world.areas.positioning.services import add_blueprint_position

        add_blueprint_position(bp, "Center", description="The centre")

        cmd = CmdSetStage()
        cmd.args = "Lone Dais"
        cmd.caller = caller
        messages: list[str] = []
        caller.msg = lambda *a, **_k: messages.append(a[0] if a else "")
        cmd.func()

        assert Position.objects.filter(room=room).count() == 1
