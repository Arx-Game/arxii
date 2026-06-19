"""Tests for ConsequenceEffect validation of positioning/reshaping effect types (#1018)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.checks.constants import EffectType, PositionDestination
from world.checks.factories import ConsequenceFactory


class PositioningEffectValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.consequence = ConsequenceFactory()

    def _effect(self, **kw):
        from world.checks.models import ConsequenceEffect

        return ConsequenceEffect(consequence=self.consequence, **kw)

    def test_create_position_requires_name(self):
        with self.assertRaises(ValidationError):
            self._effect(effect_type=EffectType.CREATE_POSITION, position_name="").clean()

    def test_create_position_valid(self):
        self._effect(
            effect_type=EffectType.CREATE_POSITION,
            position_name="floating platform",
            position_kind=PositionKind.FEATURE,
        ).clean()  # no raise

    def test_move_to_position_requires_destination(self):
        with self.assertRaises(ValidationError):
            self._effect(effect_type=EffectType.MOVE_TO_POSITION, position_destination="").clean()

    def test_move_named_requires_position_name(self):
        with self.assertRaises(ValidationError):
            self._effect(
                effect_type=EffectType.MOVE_TO_POSITION,
                position_destination=PositionDestination.NAMED,
                position_name="",
            ).clean()

    def test_move_named_valid(self):
        self._effect(
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.NAMED,
            position_name="altar",
        ).clean()  # no raise

    def test_move_actor_position_valid(self):
        self._effect(
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.ACTOR_POSITION,
        ).clean()  # no raise

    def test_sever_edge_requires_both_names(self):
        with self.assertRaises(ValidationError):
            self._effect(
                effect_type=EffectType.SEVER_EDGE, position_name="a", position_name_b=""
            ).clean()

    def test_sever_edge_valid(self):
        self._effect(
            effect_type=EffectType.SEVER_EDGE,
            position_name="altar",
            position_name_b="gate",
        ).clean()  # no raise

    def test_connect_edge_requires_both_names(self):
        with self.assertRaises(ValidationError):
            self._effect(
                effect_type=EffectType.CONNECT_EDGE, position_name="", position_name_b="gate"
            ).clean()

    def test_grant_flight_needs_no_position_fields(self):
        self._effect(effect_type=EffectType.GRANT_FLIGHT).clean()  # no raise

    def test_remove_flight_needs_no_position_fields(self):
        self._effect(effect_type=EffectType.REMOVE_FLIGHT).clean()  # no raise
