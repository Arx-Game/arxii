"""``room/aura`` resonance parsing (#2036), the magic corner of the ``room`` family.

Every other ``room`` verb is typed through the handler in
``integration_tests/test_shaping_the_house_journeys.py`` (#3657 tranche 19); the
aura switch's resonance resolution stays here as magic ground.
"""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.locations import CmdRoom


class RoomAuraParseTests(TestCase):
    """``room/aura`` resolves a resonance name to the tag/untag action's kwargs."""

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

    def test_aura_switch_routes_to_tag_room_resonance(self) -> None:
        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory(name="Copperi")
        key, kwargs = self._dispatch(["aura"], "Copperi")
        assert (key, kwargs) == ("tag_room_resonance", {"resonance_id": resonance.pk})

    def test_aura_clear_routes_to_untag_room_resonance(self) -> None:
        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory(name="Predari")
        key, kwargs = self._dispatch(["aura"], "clear Predari")
        assert (key, kwargs) == ("untag_room_resonance", {"resonance_id": resonance.pk})

    def test_aura_requires_a_resonance_name(self) -> None:
        with self.assertRaises(CommandError):
            self._dispatch(["aura"], "")

    def test_aura_unknown_resonance_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._dispatch(["aura"], "Nonexistent Resonance Name")
