"""Tests for RoomDescVariant + resolve_room_description (#3291)."""

from datetime import UTC, datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomDescVariantFactory, RoomProfileFactory
from evennia_extensions.models import RoomDescVariant
from evennia_extensions.services.room_desc_variants import resolve_room_description

_WINTER_NIGHT = datetime(1, 1, 10, 2, 0, tzinfo=UTC)  # month=1 -> WINTER; hour=2 -> NIGHT
_WINTER_DAY = datetime(1, 1, 10, 12, 0, tzinfo=UTC)  # month=1 -> WINTER; hour=12 -> DAY
_SUMMER_DAY = datetime(1, 7, 10, 12, 0, tzinfo=UTC)  # month=7 -> SUMMER; hour=12 -> DAY
_SUMMER_NIGHT = datetime(1, 7, 10, 23, 0, tzinfo=UTC)  # month=7 -> SUMMER; hour=23 -> NIGHT


class RoomDescVariantModelTests(TestCase):
    def test_requires_season_or_phase(self) -> None:
        profile = RoomProfileFactory()
        variant = RoomDescVariant(room_profile=profile, description="Bare.")
        with self.assertRaises(ValidationError):
            variant.full_clean()

    def test_season_only_is_valid(self) -> None:
        profile = RoomProfileFactory()
        variant = RoomDescVariant(room_profile=profile, season="winter", description="Cold.")
        variant.full_clean()  # should not raise

    def test_unique_constraint_on_room_season_phase(self) -> None:
        profile = RoomProfileFactory()
        RoomDescVariantFactory(room_profile=profile, season="winter", phase="night")
        with self.assertRaises(Exception):  # noqa: B017 - IntegrityError, avoid db-backend import
            RoomDescVariantFactory(room_profile=profile, season="winter", phase="night")


class ResolveRoomDescriptionTests(TestCase):
    """Fallback matrix: clock set/unset x each specificity tier (#3291)."""

    def setUp(self) -> None:
        self.profile = RoomProfileFactory()

    def test_clock_unset_returns_none(self) -> None:
        RoomDescVariantFactory(room_profile=self.profile, season="winter", description="Cold.")
        assert resolve_room_description(self.profile, None) is None

    def test_no_variants_returns_none(self) -> None:
        assert resolve_room_description(self.profile, _WINTER_NIGHT) is None

    def test_season_and_phase_variant_wins_most_specific(self) -> None:
        RoomDescVariantFactory(
            room_profile=self.profile,
            season="winter",
            phase="night",
            description="A hard, black midwinter cold.",
        )
        RoomDescVariantFactory(
            room_profile=self.profile,
            season="winter",
            phase=None,
            description="Winter, generally.",
        )
        RoomDescVariantFactory(
            room_profile=self.profile,
            season=None,
            phase="night",
            description="Night, generally.",
        )
        result = resolve_room_description(self.profile, _WINTER_NIGHT)
        assert result == "A hard, black midwinter cold."

    def test_season_only_variant_beats_phase_only(self) -> None:
        RoomDescVariantFactory(
            room_profile=self.profile, season="winter", phase=None, description="Winter."
        )
        RoomDescVariantFactory(
            room_profile=self.profile, season=None, phase="night", description="Night."
        )
        result = resolve_room_description(self.profile, _WINTER_NIGHT)
        assert result == "Winter."

    def test_phase_only_variant_used_when_season_absent(self) -> None:
        RoomDescVariantFactory(
            room_profile=self.profile, season=None, phase="night", description="Night falls."
        )
        result = resolve_room_description(self.profile, _WINTER_NIGHT)
        assert result == "Night falls."

    def test_non_matching_season_falls_back_to_none(self) -> None:
        RoomDescVariantFactory(
            room_profile=self.profile, season="summer", description="Summer heat."
        )
        assert resolve_room_description(self.profile, _WINTER_DAY) is None

    def test_summer_day_and_night_are_distinct(self) -> None:
        RoomDescVariantFactory(
            room_profile=self.profile, season="summer", phase="day", description="Bright noon."
        )
        RoomDescVariantFactory(
            room_profile=self.profile, season="summer", phase="night", description="Warm dark."
        )
        assert resolve_room_description(self.profile, _SUMMER_DAY) == "Bright noon."
        assert resolve_room_description(self.profile, _SUMMER_NIGHT) == "Warm dark."
