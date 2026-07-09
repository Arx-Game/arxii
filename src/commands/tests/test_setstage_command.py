"""setstage command (#1498) — parse telnet text into SetTheStageAction kwargs."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.setstage import CmdSetStage
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.areas.positioning.factories import PositionBlueprintFactory
from world.areas.positioning.models import Position
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


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


def _make_character(key: str, room, *, is_staff: bool) -> object:
    """Return an Evennia character connected to an account."""
    from evennia import create_object

    char = create_object("typeclasses.characters.Character", key=key, location=room, nohome=True)
    account = AccountFactory(username=f"account_{key}", is_staff=is_staff)
    char.db_account = account
    return char


def _make_staff_character(key: str, room) -> object:
    """Return an Evennia character connected to a staff account."""
    return _make_character(key, room, is_staff=True)


def _make_nonstaff_character(key: str, room) -> object:
    """Return an Evennia character connected to a non-staff account."""
    return _make_character(key, room, is_staff=False)


def _make_gm_character(key: str, room, level: str) -> object:
    """Return a Character with a live roster tenure + GMProfile at ``level``.

    ``MinimumGMLevelPrerequisite`` reads ``active_account``, which requires a
    real ``RosterTenure`` -- not just ``char.db_account`` (mirrors
    ``world/scenes/tests/test_scene_admin_services.py``'s
    ``_create_pc_with_account`` helper).
    """
    char = CharacterFactory(db_key=key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    GMProfileFactory(account=account, level=level)
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
        self.assertIn("No positions are set in this room yet.", msgs)

    def test_bare_setstage_with_default_blueprint(self) -> None:
        room = _make_room()
        blueprint = PositionBlueprintFactory(name="Hall Layout")
        profile = RoomProfileFactory(objectdb=room)
        profile.default_blueprint = blueprint
        profile.save()
        caller = _make_staff_character("stagehand", room)
        msgs = self._run("", caller)
        assert any("Default blueprint here:" in m for m in msgs)

    def test_list_lists_blueprints(self) -> None:
        PositionBlueprintFactory(name="Alpha")
        PositionBlueprintFactory(name="Beta")
        caller = _make_staff_character("listonly", _make_room())
        msgs = self._run("list", caller)
        assert any("Alpha" in m for m in msgs)
        assert any("Beta" in m for m in msgs)


class SetStageRunTests(TestCase):
    def _run(self, args: str, caller) -> list[str]:
        cmd = CmdSetStage()
        cmd.args = args
        cmd.caller = caller
        messages: list[str] = []
        caller.msg = lambda *a, **_k: messages.append(a[0] if a else "")
        cmd.func()
        return messages

    def test_setstage_name_instantiates_positions(self) -> None:
        room = _make_room()
        caller = _make_staff_character("stager", room)
        # A blueprint with one position template -> one live Position in the room.
        bp = PositionBlueprintFactory(name="Lone Dais")
        from world.areas.positioning.services import add_blueprint_position

        add_blueprint_position(bp, "Center", description="The centre")

        self._run("Lone Dais", caller)

        assert Position.objects.filter(room=room).count() == 1

    def test_nonstaff_non_gm_caller_is_blocked(self) -> None:
        """A caller with no GMProfile at all is refused (#2117)."""
        room = _make_room()
        caller = _make_nonstaff_character("poser", room)
        bp = PositionBlueprintFactory(name="Lone Dais")
        from world.areas.positioning.services import add_blueprint_position

        add_blueprint_position(bp, "Center", description="The centre")

        msgs = self._run("Lone Dais", caller)

        assert any("GM trust required." in m for m in msgs)
        assert Position.objects.filter(room=room).count() == 0

    def test_starting_gm_caller_succeeds(self) -> None:
        """A STARTING-tier GM (no staff flag) can setstage (#2117)."""
        room = _make_room()
        caller = _make_gm_character("starter", room, GMLevel.STARTING)
        bp = PositionBlueprintFactory(name="Lone Dais")
        from world.areas.positioning.services import add_blueprint_position

        add_blueprint_position(bp, "Center", description="The centre")

        self._run("Lone Dais", caller)

        assert Position.objects.filter(room=room).count() == 1

    def test_setstage_replace_replaces_existing_position_grid(self) -> None:
        room = _make_room()
        caller = _make_staff_character("replacer", room)
        from world.areas.positioning.services import add_blueprint_position

        bp_a = PositionBlueprintFactory(name="Lone Dais")
        add_blueprint_position(bp_a, "Center", description="The centre")
        bp_b = PositionBlueprintFactory(name="Tight Alley")
        add_blueprint_position(bp_b, "Alley", description="A narrow passage")

        self._run("Lone Dais", caller)
        assert Position.objects.filter(room=room).count() == 1
        assert Position.objects.filter(room=room, name="Center").exists()

        self._run("Tight Alley replace", caller)
        positions = Position.objects.filter(room=room)
        assert positions.count() == 1
        assert positions.first().name == "Alley"
        assert not Position.objects.filter(room=room, name="Center").exists()
