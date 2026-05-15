"""Tests for the has_affinity_resonance filter DSL operator."""

from types import SimpleNamespace

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from flows.filters.evaluator import evaluate_filter
from world.magic.factories import (
    AffinityFactory,
    ResonanceFactory,
    RoomAuraProfileFactory,
    RoomResonanceFactory,
)


def _make_room_with_resonances(resonances: list) -> object:
    """Build a room ObjectDB -> RoomProfile -> optional RoomAuraProfile -> RoomResonance rows.

    Returns the ObjectDB (the 'room' the filter receives via payload['location']).
    If `resonances` is empty, skip the RoomAuraProfile creation (room is non-magical).
    """
    room_profile = RoomProfileFactory()
    if not resonances:
        return room_profile.objectdb
    aura_profile = RoomAuraProfileFactory(room_profile=room_profile)
    for resonance in resonances:
        RoomResonanceFactory(room_aura_profile=aura_profile, resonance=resonance)
    return room_profile.objectdb


class HasAffinityResonanceFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial = AffinityFactory(name="Celestial (T6 test)")
        cls.abyssal = AffinityFactory(name="Abyssal (T6 test)")
        cls.light = ResonanceFactory(name="Light (T6 test)", affinity=cls.celestial)
        cls.shadow = ResonanceFactory(name="Shadow (T6 test)", affinity=cls.abyssal)

    def test_true_when_room_has_named_affinity_resonance(self) -> None:
        room = _make_room_with_resonances([self.light])
        payload = SimpleNamespace(location=room)
        spec = {"path": "location", "op": "has_affinity_resonance", "value": "Celestial (T6 test)"}
        self.assertTrue(evaluate_filter(spec, payload, self_ref=None))

    def test_false_when_room_has_other_affinity_only(self) -> None:
        room = _make_room_with_resonances([self.shadow])
        payload = SimpleNamespace(location=room)
        spec = {"path": "location", "op": "has_affinity_resonance", "value": "Celestial (T6 test)"}
        self.assertFalse(evaluate_filter(spec, payload, self_ref=None))

    def test_false_when_room_has_no_aura_profile(self) -> None:
        room = _make_room_with_resonances([])  # no aura profile at all
        payload = SimpleNamespace(location=room)
        spec = {"path": "location", "op": "has_affinity_resonance", "value": "Celestial (T6 test)"}
        self.assertFalse(evaluate_filter(spec, payload, self_ref=None))

    def test_true_when_room_has_multiple_celestial_resonances(self) -> None:
        another_celestial = ResonanceFactory(name="Sanctity (T6 test)", affinity=self.celestial)
        room = _make_room_with_resonances([self.light, another_celestial])
        payload = SimpleNamespace(location=room)
        spec = {"path": "location", "op": "has_affinity_resonance", "value": "Celestial (T6 test)"}
        self.assertTrue(evaluate_filter(spec, payload, self_ref=None))
