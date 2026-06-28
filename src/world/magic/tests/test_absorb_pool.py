"""Tests for absorb_pool force-field handler (#1584).

SQLite-safe: the handler uses a plain .filter() with no DISTINCT ON; no
apply_condition calls. Direct factory construction throughout.

Four cases:
  1. Buffer 20 vs 30 damage → amount drops to 10, instance deleted (buffer spent).
  2. Second 30-damage hit after buffer gone → amount unchanged (no absorb instance).
  3. payload.amount == 0 guard → immediate return, buffer untouched.
  4. anima.current < reactive_anima_cost → fizzle (amount and buffer unchanged).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.conditions.constants import FORCE_FIELD_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.factories import CharacterAnimaFactory
from world.magic.services.effect_handlers import absorb_pool


def _make_bearer_with_buffer(
    *,
    anima_current: int = 10,
    reactive_anima_cost: int = 1,
    absorb_remaining: int = 20,
):
    """Return (bearer ObjectDB, CharacterAnima, ConditionInstance) ready for a test."""
    bearer = CharacterFactory()
    anima = CharacterAnimaFactory(character=bearer, current=anima_current, maximum=10)
    template = ConditionTemplateFactory(
        name=FORCE_FIELD_CONDITION_NAME,
        reactive_anima_cost=reactive_anima_cost,
    )
    instance = ConditionInstanceFactory(
        condition=template,
        target=bearer,
        absorb_remaining=absorb_remaining,
    )
    return bearer, anima, instance


def _payload(bearer, amount: int) -> DamagePreApplyPayload:
    return DamagePreApplyPayload(
        target=bearer,
        amount=amount,
        damage_type=None,
        source=DamageSource(type="environment", ref=None),
    )


class AbsorbPoolHandlerTests(TestCase):
    """absorb_pool drains a force-field buffer to soak incoming DAMAGE_PRE_APPLY."""

    def test_partial_absorb_reduces_payload_and_expires_instance(self) -> None:
        """30 incoming vs 20 buffer: payload reduced to 10, instance deleted."""
        bearer, anima, instance = _make_bearer_with_buffer(
            anima_current=10,
            reactive_anima_cost=1,
            absorb_remaining=20,
        )
        payload = _payload(bearer, amount=30)

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 10)
        # Buffer fully spent → instance must be deleted.
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
        # Anima decremented by reactive cost.
        anima.refresh_from_db()
        self.assertEqual(anima.current, 9)

    def test_second_hit_passes_through_after_buffer_gone(self) -> None:
        """After the buffer is fully consumed, subsequent hits pass unchanged."""
        bearer, _anima, _instance = _make_bearer_with_buffer(
            anima_current=10,
            reactive_anima_cost=1,
            absorb_remaining=20,
        )
        # Burn the buffer.
        absorb_pool(payload=_payload(bearer, amount=30))

        # Second hit — no buffer remains.
        payload2 = _payload(bearer, amount=30)
        absorb_pool(payload=payload2)

        self.assertEqual(payload2.amount, 30)

    def test_zero_amount_guard_leaves_buffer_intact(self) -> None:
        """payload.amount == 0 → return immediately; buffer is not touched."""
        bearer, _anima, instance = _make_bearer_with_buffer(
            anima_current=10,
            reactive_anima_cost=1,
            absorb_remaining=20,
        )
        payload = _payload(bearer, amount=0)

        absorb_pool(payload=payload)

        instance.refresh_from_db()
        self.assertEqual(instance.absorb_remaining, 20)

    def test_fizzle_when_anima_insufficient(self) -> None:
        """anima.current < reactive_anima_cost → fizzle; amount and buffer unchanged."""
        bearer, _anima, instance = _make_bearer_with_buffer(
            anima_current=0,
            reactive_anima_cost=1,
            absorb_remaining=20,
        )
        payload = _payload(bearer, amount=30)

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 30)
        instance.refresh_from_db()
        self.assertEqual(instance.absorb_remaining, 20)
