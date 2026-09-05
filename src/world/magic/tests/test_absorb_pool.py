"""Tests for absorb_pool force-field handler (#1584).

SQLite-safe: the handler uses a plain .filter() with no DISTINCT ON; no
apply_condition calls. Direct factory construction throughout.

Four cases:
  1. Buffer 20 vs 30 damage → amount drops to 10, instance deleted (buffer spent).
  2. Second 30-damage hit after buffer gone → amount unchanged (no absorb instance).
  3. payload.amount == 0 guard → immediate return, buffer untouched.
  4. anima.current < reactive_anima_cost → fizzle (amount and buffer unchanged).
"""

from unittest.mock import patch

from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.character_sheets.factories import CharacterSheetFactory
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
    bearer = CharacterSheetFactory().character
    anima = CharacterAnimaFactory(character=bearer.sheet_data, current=anima_current, maximum=10)
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
        """anima.current < reactive_anima_cost -> fizzle; amount/buffer unchanged; payer told."""
        bearer, _anima, instance = _make_bearer_with_buffer(
            anima_current=0,
            reactive_anima_cost=1,
            absorb_remaining=20,
        )
        payload = _payload(bearer, amount=30)

        with (
            patch("world.scenes.interaction_services.narrate_privately") as private,
            patch("world.combat.services._broadcast_commitment_line") as room,
        ):
            absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 30)
        instance.refresh_from_db()
        self.assertEqual(instance.absorb_remaining, 20)
        # #3574: self-cast ward, payer is the bearer: one private line. Out of
        # combat there is no encounter, so no room line.
        private.assert_called_once()
        self.assertEqual(private.call_args.args[0].pk, bearer.pk)
        self.assertIn("cannot pay its fee", private.call_args.args[1])
        self.assertIn(instance.condition.name, private.call_args.args[1])
        room.assert_not_called()

    def test_fizzle_of_an_ally_ward_tells_caster_and_bearer(self) -> None:
        bearer, _anima, instance = _make_bearer_with_buffer(
            anima_current=10, reactive_anima_cost=1, absorb_remaining=20
        )
        caster = CharacterSheetFactory().character
        CharacterAnimaFactory(character=caster.sheet_data, current=0, maximum=10)
        instance.source_character = caster
        instance.save(update_fields=["source_character"])
        payload = _payload(bearer, amount=30)

        with patch("world.scenes.interaction_services.narrate_privately") as private:
            absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 30)
        by_pk = {c.args[0].pk: c.args[1] for c in private.call_args_list}
        self.assertEqual(set(by_pk), {caster.pk, bearer.pk})
        self.assertIn("cannot pay its fee", by_pk[caster.pk])
        self.assertIn(str(bearer), by_pk[caster.pk])
        self.assertIn("does not answer the blow", by_pk[bearer.pk])
        self.assertNotIn("fee", by_pk[bearer.pk])

    def test_fizzle_inside_an_encounter_adds_a_room_line(self) -> None:
        from world.combat.factories import CombatEncounterFactory
        from world.combat.services import active_combat_engagement_for, add_participant
        from world.scenes.constants import RoundStatus

        bearer, _anima, _instance = _make_bearer_with_buffer(
            anima_current=0, reactive_anima_cost=1, absorb_remaining=20
        )
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        # add_participant creates both the CombatParticipant row AND the
        # COMBAT CharacterEngagement (_create_participant ->
        # _ensure_combat_engagement) so active_combat_engagement_for(bearer)
        # resolves for real, unmocked, below.
        add_participant(encounter, bearer.sheet_data)
        self.assertIsNotNone(active_combat_engagement_for(bearer))
        payload = _payload(bearer, amount=30)

        with (
            patch("world.scenes.interaction_services.narrate_privately"),
            patch("world.combat.services._broadcast_commitment_line") as room,
        ):
            absorb_pool(payload=payload)

        room.assert_called_once()
        self.assertEqual(room.call_args.args[0].pk, encounter.pk)
        room_line = room.call_args.args[1]
        self.assertIn("flickers and fails", room_line)
        self.assertIn(str(bearer), room_line)
        # Controller ruling: factory-generated character names contain digits,
        # so assertNotRegex(r"\d") on the raw line cannot pass verbatim. Strip
        # the known character name first, then assert no digit remains: the
        # intent (room lines carry no numbers) is preserved.
        self.assertNotRegex(room_line.replace(str(bearer), ""), r"\d")
