"""Tests for flows.service_functions.affinity.compute_intensity_difficulty."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from flows.service_functions.affinity import compute_intensity_difficulty
from world.magic.factories import (
    AffinityFactory,
    ResonanceFactory,
    RoomAuraProfileFactory,
    RoomResonanceFactory,
)


def _make_room_with_resonances(resonances: list) -> object:
    """Build a room ObjectDB + RoomProfile + (optional) RoomAuraProfile + RoomResonance.

    Returns the room ObjectDB. If `resonances` is empty, no aura profile is created.
    Pattern mirrors test_filters/test_has_affinity_resonance.py helper.
    """
    room_profile = RoomProfileFactory()
    if not resonances:
        return room_profile.objectdb
    aura = RoomAuraProfileFactory(room_profile=room_profile)
    for res in resonances:
        RoomResonanceFactory(room_aura_profile=aura, resonance=res)
    return room_profile.objectdb


class ComputeIntensityDifficultyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial = AffinityFactory(name="Celestial (T7 test)")
        cls.abyssal = AffinityFactory(name="Abyssal (T7 test)")
        cls.light = ResonanceFactory(name="Light (T7 test)", affinity=cls.celestial)
        cls.sanctity = ResonanceFactory(name="Sanctity (T7 test)", affinity=cls.celestial)
        cls.radiance = ResonanceFactory(name="Radiance (T7 test)", affinity=cls.celestial)
        cls.shadow = ResonanceFactory(name="Shadow (T7 test)", affinity=cls.abyssal)

    def test_returns_base_for_room_with_no_aura(self) -> None:
        room = _make_room_with_resonances([])
        result = compute_intensity_difficulty(
            room=room,
            affinity_name="Celestial (T7 test)",
            base_difficulty=10,
            per_resonance_modifier=5,
        )
        self.assertEqual(result, 10)

    def test_scales_with_celestial_count_one(self) -> None:
        room = _make_room_with_resonances([self.light])
        result = compute_intensity_difficulty(
            room=room,
            affinity_name="Celestial (T7 test)",
            base_difficulty=10,
            per_resonance_modifier=5,
        )
        self.assertEqual(result, 15)

    def test_three_resonances_yields_twenty_five(self) -> None:
        room = _make_room_with_resonances([self.light, self.sanctity, self.radiance])
        result = compute_intensity_difficulty(
            room=room,
            affinity_name="Celestial (T7 test)",
            base_difficulty=10,
            per_resonance_modifier=5,
        )
        self.assertEqual(result, 25)

    def test_ignores_other_affinity_resonances(self) -> None:
        room = _make_room_with_resonances([self.shadow, self.light])
        result = compute_intensity_difficulty(
            room=room,
            affinity_name="Celestial (T7 test)",
            base_difficulty=10,
            per_resonance_modifier=5,
        )
        self.assertEqual(result, 15)  # Only the Celestial resonance counts.

    def test_per_resonance_modifier_honored(self) -> None:
        room = _make_room_with_resonances([self.light, self.sanctity])
        result = compute_intensity_difficulty(
            room=room,
            affinity_name="Celestial (T7 test)",
            base_difficulty=5,
            per_resonance_modifier=10,
        )
        self.assertEqual(result, 25)  # 5 + 2*10
