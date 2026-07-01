"""Sunlight exposure reconciliation: outdoor + day-phase gating (#1588)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.game_clock.constants import TimePhase
from world.species.factories import ensure_sunlight_exposure_content
from world.species.services import reconcile_sunlight_exposure


def _phase(name: str) -> TimePhase:
    return TimePhase(name)


class ReconcileSunlightExposureTest(TestCase):
    """The reconciliation applies/removes Sunlight Exposure based on outdoor + phase.

    These are unit tests for the gating logic; the full journey (DoT -> peril
    pipeline) lives in the scenes sunlight-exposure E2E.
    """

    @classmethod
    def setUpTestData(cls):
        cls.template = ensure_sunlight_exposure_content()

    def test_no_sheet_is_noop(self):
        """A character without sheet_data (NPC/non-puppet) is a no-op."""
        char = MagicMock()
        del char.sheet_data  # getattr returns MagicMock by default; force AttributeError
        with patch("world.species.services.apply_condition") as ac:
            reconcile_sunlight_exposure(char, room=None)
        ac.assert_not_called()

    def test_outdoor_day_applies_condition(self):
        """Outdoors during DAY with a sunlight drawback -> condition applied + round ensured."""
        char, room = self._vampire(outdoor=True)
        with (
            patch("world.species.services.has_condition", return_value=False),
            patch("world.species.services.apply_condition") as ac,
            patch("world.species.services.ensure_round_for_acute_condition") as er,
            patch(
                "world.species.services.get_ic_phase",
                return_value=_phase("day"),
            ),
        ):
            reconcile_sunlight_exposure(char, room=room)
        ac.assert_called_once_with(char, self.template)
        er.assert_called_once()

    def test_indoor_does_not_apply(self):
        """Indoors during DAY -> no condition applied."""
        char, room = self._vampire(outdoor=False)
        with (
            patch("world.species.services.has_condition", return_value=False),
            patch("world.species.services.apply_condition") as ac,
            patch(
                "world.species.services.get_ic_phase",
                return_value=_phase("day"),
            ),
        ):
            reconcile_sunlight_exposure(char, room=room)
        ac.assert_not_called()

    def test_night_does_not_apply(self):
        """Outdoors at NIGHT -> no condition applied."""
        char, room = self._vampire(outdoor=True)
        with (
            patch("world.species.services.has_condition", return_value=False),
            patch("world.species.services.apply_condition") as ac,
            patch(
                "world.species.services.get_ic_phase",
                return_value=_phase("night"),
            ),
        ):
            reconcile_sunlight_exposure(char, room=room)
        ac.assert_not_called()

    def test_already_active_does_not_reapply(self):
        """Outdoors during DAY but condition already active -> no re-apply, no remove."""
        char, room = self._vampire(outdoor=True)
        with (
            patch("world.species.services.has_condition", return_value=True),
            patch("world.species.services.apply_condition") as ac,
            patch("world.species.services.remove_condition") as rc,
            patch(
                "world.species.services.get_ic_phase",
                return_value=_phase("day"),
            ),
        ):
            reconcile_sunlight_exposure(char, room=room)
        ac.assert_not_called()
        rc.assert_not_called()

    def test_removes_when_no_longer_exposed(self):
        """Condition active but now indoor -> removed."""
        char, room = self._vampire(outdoor=False)
        with (
            patch("world.species.services.has_condition", return_value=True),
            patch("world.species.services.remove_condition") as rc,
            patch(
                "world.species.services.get_ic_phase",
                return_value=_phase("day"),
            ),
        ):
            reconcile_sunlight_exposure(char, room=room)
        rc.assert_called_once_with(char, self.template)

    def _vampire(self, *, outdoor: bool):
        """Build a mock character + room with a sunlight drawback species."""
        char = MagicMock()
        char.sheet_data.species = MagicMock(pk=1)
        char.sheet_data.species_id = 1
        char.sheet_data.character = char
        room = MagicMock()
        room.room_profile.is_outdoor = outdoor
        patches = [
            patch(
                "world.species.services._has_sunlight_drawback",
                return_value=True,
            ),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return char, room
