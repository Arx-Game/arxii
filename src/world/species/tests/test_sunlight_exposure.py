"""Sunlight exposure reconciliation: outdoor + day-phase gating (#1588)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.conditions.services import has_condition
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
            # Shelter (#1744) is a separate axis covered by its own real-fixture test class
            # below; these mocked rooms have no real RoomProfile/AreaClosure to resolve it against.
            patch(
                "world.species.services._room_shelters_radiant",
                return_value=False,
            ),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return char, room


class ReconcileSunlightExposureLocationShelterTest(TestCase):
    """Location-shelter (#1744): a shaded outdoor room suppresses Sunlight Exposure.

    Uses real fixtures (not mocks) because the shelter gate reads a real
    ``LocationValueOverride`` row through ``world.locations.services.hazard_is_covered``.
    Stays on the SQLite fast tier: ``should_expose`` resolves False here, so
    ``apply_condition``/``remove_condition`` (the PG-only ``DISTINCT ON`` path) never fire.
    """

    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import GiftFactory
        from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory

        self.template = ensure_sunlight_exposure_content()

        species = SpeciesFactory(name="Vampire")
        gift = GiftFactory()
        SpeciesGiftGrantFactory(species=species, gift=gift, drawback_condition=self.template)

        self.room_profile = RoomProfileFactory(is_outdoor=True)
        self.outdoor_room = self.room_profile.objectdb

        sheet = CharacterSheetFactory(species=species)
        self.vampire_character = sheet.character
        self.vampire_character.db_location = self.outdoor_room
        self.vampire_character.save(update_fields=["db_location"])

    def test_shaded_outdoor_room_suppresses_sunlight_exposure(self):
        from world.conditions.factories import ensure_radiant_damage_type
        from world.locations.constants import KeyType
        from world.locations.models import LocationValueOverride

        radiant = ensure_radiant_damage_type()
        LocationValueOverride.objects.create(
            parent_type="room",
            room_profile=self.outdoor_room.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=radiant,
            value=1,
        )
        with patch(
            "world.species.services.get_ic_phase",
            return_value=TimePhase.DAY,
        ):
            reconcile_sunlight_exposure(self.vampire_character, self.outdoor_room)
        self.assertFalse(has_condition(self.vampire_character, self.template))
