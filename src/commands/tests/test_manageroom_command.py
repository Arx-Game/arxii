"""``room`` command family (#1470 editor + #670 builder) — switch parsing → action kwargs."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.locations import CmdManageRoom, CmdRoom, _split_trailing_kwargs


class RoomCommandParseTests(TestCase):
    """Parse-level tests: each switch routes to the right action with the right kwargs."""

    def _dispatch(self, switches: list[str], args: str) -> tuple[str, dict]:
        cmd = CmdRoom()
        cmd.switches = switches
        cmd.args = args
        captured: dict = {}

        def fake_run(action_key: str, **kwargs) -> None:
            captured["key"] = action_key
            captured["kwargs"] = kwargs

        cmd._run = fake_run
        cmd._dispatch()
        return captured["key"], captured["kwargs"]

    def test_legacy_alias_still_importable(self) -> None:
        assert CmdManageRoom is CmdRoom
        assert "manageroom" in CmdRoom.aliases
        assert "build" in CmdRoom.aliases

    def test_name_switch_routes_to_edit_room(self) -> None:
        key, kwargs = self._dispatch(["name"], "  The Solar  ")
        assert key == "edit_room"
        assert kwargs == {"name": "The Solar"}

    def test_desc_switch_routes_to_edit_room(self) -> None:
        key, kwargs = self._dispatch(["desc"], "Warm light, worn rugs.")
        assert key == "edit_room"
        assert kwargs == {"description": "Warm light, worn rugs."}

    def test_public_yes_no(self) -> None:
        assert self._dispatch(["public"], "yes")[1] == {"is_public": True}
        assert self._dispatch(["public"], "no")[1] == {"is_public": False}

    def test_dig_minimal(self) -> None:
        key, kwargs = self._dispatch(["dig"], "north=Kitchen")
        assert key == "dig_room"
        assert kwargs == {"direction": "north", "name": "Kitchen", "like": "", "size": ""}

    def test_dig_with_like_and_size(self) -> None:
        key, kwargs = self._dispatch(["dig"], "north=Grand Hall like=West Corridor size=Snug")
        assert key == "dig_room"
        assert kwargs["name"] == "Grand Hall"
        assert kwargs["like"] == "West Corridor"
        assert kwargs["size"] == "Snug"

    def test_size_switch_routes_to_resize(self) -> None:
        key, kwargs = self._dispatch(["size"], "Snug")
        assert key == "resize_room"
        assert kwargs == {"size": "Snug"}

    def test_drop_requires_confirm(self) -> None:
        with self.assertRaises(CommandError):
            self._dispatch(["drop"], "")
        key, _kwargs = self._dispatch(["drop"], "confirm")
        assert key == "remove_room"

    def test_addexit_requires_both_names(self) -> None:
        with self.assertRaises(CommandError):
            self._dispatch(["addexit"], "Study=through the oak door")
        key, kwargs = self._dispatch(["addexit"], "Study=through the oak door,back to hall")
        assert key == "link_rooms"
        assert kwargs == {
            "to": "Study",
            "name_there": "through the oak door",
            "name_back": "back to hall",
        }

    def test_removeexit_and_renameexit(self) -> None:
        key, kwargs = self._dispatch(["removeexit"], "north")
        assert (key, kwargs) == ("unlink_rooms", {"exit": "north"})
        key, kwargs = self._dispatch(["renameexit"], "north=grand stair")
        assert (key, kwargs) == ("rename_exit", {"exit": "north", "name": "grand stair"})

    def test_home_routes_to_set_primary_home(self) -> None:
        key, kwargs = self._dispatch(["home"], "")
        assert (key, kwargs) == ("set_primary_home", {})

    def test_style_switch_routes_to_set_building_style(self) -> None:
        key, kwargs = self._dispatch(["style"], "Antique Imperial")
        assert (key, kwargs) == ("set_building_style", {"style": "Antique Imperial"})

    def test_extend_routes_added_budget(self) -> None:
        key, kwargs = self._dispatch(["extend"], "50")
        assert (key, kwargs) == ("start_building_extension", {"added_budget": "50"})

    def test_no_switch_raises_usage(self) -> None:
        with self.assertRaises(CommandError):
            self._dispatch([], "anything")

    def test_name_requires_a_value(self) -> None:
        with self.assertRaises(CommandError):
            self._dispatch(["name"], "")


class SplitTrailingKwargsTests(TestCase):
    def test_values_may_contain_spaces(self) -> None:
        text, extra = _split_trailing_kwargs(
            "Grand Hall like=West Corridor size=Snug", ("like", "size")
        )
        assert text == "Grand Hall"
        assert extra == {"like": "West Corridor", "size": "Snug"}

    def test_no_kwargs_passthrough(self) -> None:
        text, extra = _split_trailing_kwargs("Kitchen", ("like", "size"))
        assert text == "Kitchen"
        assert extra == {}
