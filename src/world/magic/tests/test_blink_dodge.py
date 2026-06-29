"""Tests for blink_dodge reactive teleport-dodge handler (#1584).

SQLite-safe: no DISTINCT ON / apply_condition calls. Direct factory construction
throughout; all assertions are positional + payload state.

Four cases:
  (a) anima >= cost → payload.amount == 0, cost debited, bearer repositioned.
  (b) anima < cost → fizzle: payload.amount unchanged, no move, no debit.
  (c) payload.amount == 0 on entry → immediate return (guard fires, no-op).
  (d) cost paid but only ONE position in room → payload.amount == 0 still (no crash).
"""

from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.areas.positioning.factories import ObjectPositionFactory, PositionFactory
from world.areas.positioning.services import position_of
from world.conditions.constants import BLINK_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.factories import CharacterAnimaFactory
from world.magic.services.effect_handlers import blink_dodge

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_blink_setup(*, anima_current: int = 10, reactive_anima_cost: int = 2):
    """Return (bearer, pos_a, pos_b, anima, condition_instance).

    Bearer is placed at pos_a in a two-position room.
    """
    pos_a = PositionFactory()
    pos_b = PositionFactory(room=pos_a.room)
    op = ObjectPositionFactory(position=pos_a)
    bearer = op.objectdb
    anima = CharacterAnimaFactory(character=bearer, current=anima_current, maximum=10)
    template = ConditionTemplateFactory(
        name=BLINK_CONDITION_NAME,
        reactive_anima_cost=reactive_anima_cost,
    )
    instance = ConditionInstanceFactory(condition=template, target=bearer)
    return bearer, pos_a, pos_b, anima, instance


def _make_single_position_setup(*, anima_current: int = 10, reactive_anima_cost: int = 2):
    """Return (bearer, pos_a, anima, condition_instance) — ONE position only."""
    pos_a = PositionFactory()
    op = ObjectPositionFactory(position=pos_a)
    bearer = op.objectdb
    anima = CharacterAnimaFactory(character=bearer, current=anima_current, maximum=10)
    template = ConditionTemplateFactory(
        name=BLINK_CONDITION_NAME,
        reactive_anima_cost=reactive_anima_cost,
    )
    instance = ConditionInstanceFactory(condition=template, target=bearer)
    return bearer, pos_a, anima, instance


def _payload(bearer, amount: int) -> DamagePreApplyPayload:
    return DamagePreApplyPayload(
        target=bearer,
        amount=amount,
        damage_type=None,
        source=DamageSource(type="environment", ref=None),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class BlinkDodgeHandlerTests(TestCase):
    """blink_dodge: highest-priority DAMAGE_PRE_APPLY interceptor (#1584)."""

    def test_a_dodge_succeeds_zeros_payload_debits_anima_moves_bearer(self) -> None:
        """(a) anima >= cost: payload zeroed, anima debited, bearer at the other position."""
        bearer, pos_a, pos_b, anima, _instance = _make_blink_setup(
            anima_current=10,
            reactive_anima_cost=2,
        )
        payload = _payload(bearer, amount=15)

        blink_dodge(payload=payload)

        # Damage fully avoided.
        self.assertEqual(payload.amount, 0)
        # Anima debited by reactive_anima_cost.
        anima.refresh_from_db()
        self.assertEqual(anima.current, 8)
        # Bearer relocated to the other position in the room.
        current_pos = position_of(bearer)
        self.assertIsNotNone(current_pos)
        self.assertNotEqual(current_pos, pos_a)
        self.assertEqual(current_pos, pos_b)

    def test_b_fizzle_when_anima_insufficient(self) -> None:
        """(b) anima < cost: payload unchanged, no move, anima unchanged."""
        bearer, pos_a, _pos_b, anima, _instance = _make_blink_setup(
            anima_current=0,
            reactive_anima_cost=2,
        )
        payload = _payload(bearer, amount=15)

        blink_dodge(payload=payload)

        # Attack lands unchanged.
        self.assertEqual(payload.amount, 15)
        # No movement.
        self.assertEqual(position_of(bearer), pos_a)
        # Anima untouched.
        anima.refresh_from_db()
        self.assertEqual(anima.current, 0)

    def test_c_zero_amount_guard_returns_immediately(self) -> None:
        """(c) payload.amount == 0: immediate return; nothing changes."""
        bearer, pos_a, _pos_b, anima, _instance = _make_blink_setup(
            anima_current=10,
            reactive_anima_cost=2,
        )
        payload = _payload(bearer, amount=0)

        blink_dodge(payload=payload)

        # payload stays at 0 (guard triggered).
        self.assertEqual(payload.amount, 0)
        # Position unchanged.
        self.assertEqual(position_of(bearer), pos_a)
        # Anima untouched (guard fires before any spend attempt).
        anima.refresh_from_db()
        self.assertEqual(anima.current, 10)

    def test_d_single_position_room_dodge_still_zeros_payload(self) -> None:
        """(d) cost paid but no alternate position exists: payload zeroed, no crash, no move."""
        bearer, pos_a, anima, _instance = _make_single_position_setup(
            anima_current=10,
            reactive_anima_cost=2,
        )
        payload = _payload(bearer, amount=15)

        blink_dodge(payload=payload)

        # Dodge succeeds even without a destination (avoidance is the mechanic).
        self.assertEqual(payload.amount, 0)
        # Bearer stays at the only available position.
        self.assertEqual(position_of(bearer), pos_a)
        # Anima was debited (cost was paid before discovering no destination).
        anima.refresh_from_db()
        self.assertEqual(anima.current, 8)
