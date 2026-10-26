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

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
)
from world.areas.positioning.factories import ObjectPositionFactory, PositionFactory
from world.areas.positioning.services import position_of
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import BLINK_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionTemplate
from world.magic.factories import CharacterAnimaFactory
from world.magic.services.effect_handlers import BLINK_DODGE_HANDLER_PATH, blink_dodge

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _blink_template(*, reactive_anima_cost: int) -> ConditionTemplate:
    """A blink ward: a template whose DAMAGE_PRE_APPLY trigger flow calls blink_dodge."""
    template = ConditionTemplateFactory(
        name=BLINK_CONDITION_NAME,
        reactive_anima_cost=reactive_anima_cost,
    )
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name=BLINK_DODGE_HANDLER_PATH,
    )
    template.reactive_triggers.add(
        TriggerDefinitionFactory(flow_definition=flow, event_name=EventName.DAMAGE_PRE_APPLY)
    )
    return template


def _make_blink_setup(*, anima_current: int = 10, reactive_anima_cost: int = 2):
    """Return (bearer, pos_a, pos_b, anima, condition_instance).

    Bearer is placed at pos_a in a two-position room.
    """
    pos_a = PositionFactory()
    pos_b = PositionFactory(room=pos_a.room)
    op = ObjectPositionFactory(position=pos_a)
    bearer = op.objectdb
    sheet = CharacterSheetFactory(character=bearer)
    anima = CharacterAnimaFactory(character=sheet, current=anima_current, maximum=10)
    template = _blink_template(reactive_anima_cost=reactive_anima_cost)
    instance = ConditionInstanceFactory(condition=template, target=bearer)
    return bearer, pos_a, pos_b, anima, instance


def _make_single_position_setup(*, anima_current: int = 10, reactive_anima_cost: int = 2):
    """Return (bearer, pos_a, anima, condition_instance) — ONE position only."""
    pos_a = PositionFactory()
    op = ObjectPositionFactory(position=pos_a)
    bearer = op.objectdb
    sheet = CharacterSheetFactory(character=bearer)
    anima = CharacterAnimaFactory(character=sheet, current=anima_current, maximum=10)
    template = _blink_template(reactive_anima_cost=reactive_anima_cost)
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

    def test_a_dodge_succeeds_zeros_payload_debits_anima_stays_without_a_plan(self) -> None:
        """(a) anima >= cost: payload zeroed, anima debited; with no dodge plan she stays put.

        The game never picks a landing for her (#4676).
        """
        bearer, pos_a, _pos_b, anima, _instance = _make_blink_setup(
            anima_current=10,
            reactive_anima_cost=2,
        )
        payload = _payload(bearer, amount=15)

        blink_dodge(payload=payload)

        self.assertEqual(payload.amount, 0)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 8)
        self.assertEqual(position_of(bearer), pos_a)

    def test_a_dodge_roll_in_progress_leaves_the_hit_to_the_roll(self) -> None:
        """During an NPC attack the ward is a dodge source; this handler steps aside."""
        from world.combat.services.reactions import dodge_roll_active

        bearer, pos_a, _pos_b, anima, _instance = _make_blink_setup(
            anima_current=10,
            reactive_anima_cost=2,
        )
        payload = _payload(bearer, amount=15)

        with dodge_roll_active():
            blink_dodge(payload=payload)

        self.assertEqual(payload.amount, 15)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 10)
        self.assertEqual(position_of(bearer), pos_a)

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
