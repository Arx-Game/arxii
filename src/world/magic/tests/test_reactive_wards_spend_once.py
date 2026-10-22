"""A once-only (``UNTIL_USED``) reactive ward ends when it answers a blow (#4584).

``reflect_damage``, ``blink_dodge``, ``absorb_pool`` and ``strike_back`` each spend
their ward through ``spend_condition_use`` after a successful fire. A ward that
fizzles was not used, and a lasting ward is never spent by use. The wards are named
unlike any seed (the handler path or the field designates them), and the blink ward
sits on an NPC opponent's body, which has no sheet.
"""

from unittest.mock import patch

from django.db import transaction
from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.combat.damage_source import classify_source
from world.combat.factories import CombatOpponentFactory
from world.combat.services import apply_damage_to_participant
from world.conditions import services as condition_services
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition
from world.magic.services.effect_handlers import (
    BLINK_DODGE_HANDLER_PATH,
    REFLECT_DAMAGE_HANDLER_PATH,
    absorb_pool,
    blink_dodge,
    reflect_damage,
)
from world.magic.tests.test_reactive_handlers_designate_by_field import _bearer, _ward_template
from world.magic.tests.test_strike_back import _StrikeBackFixture


def _ward(
    name: str,
    handler_path: str,
    *,
    cost: int = 2,
    duration_type: str = DurationType.UNTIL_USED,
) -> ConditionTemplate:
    template = _ward_template(name, handler_path, cost=cost)
    template.default_duration_type = duration_type
    template.save(update_fields=["default_duration_type"])
    return template


def _blow(target, amount: int, source: DamageSource) -> DamagePreApplyPayload:
    return DamagePreApplyPayload(target=target, amount=amount, damage_type=None, source=source)


class ReactiveWardsSpendOnceTests(TestCase):
    def test_a_once_only_reflect_ward_ends_after_one_bounce(self) -> None:
        bearer, _anima = _bearer()
        inst = ConditionInstanceFactory(
            condition=_ward("Glass Rebuke 4584", REFLECT_DAMAGE_HANDLER_PATH), target=bearer
        )
        opponent = CombatOpponentFactory(health=50, soak_value=0)
        payload = _blow(bearer, 20, classify_source(opponent))

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_a_once_only_blink_on_an_npc_ends_after_one_dodge(self) -> None:
        npc = CombatOpponentFactory().objectdb
        inst = ConditionInstanceFactory(
            condition=_ward("Smoke Slip 4584", BLINK_DODGE_HANDLER_PATH, cost=0), target=npc
        )
        payload = _blow(npc, 15, DamageSource(type="environment", ref=None))

        blink_dodge(payload=payload)

        self.assertEqual(payload.amount, 0)
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_a_once_only_barrier_ends_after_its_first_soak(self) -> None:
        bearer, _anima = _bearer()
        template = ConditionTemplateFactory(
            name="Paper Bulwark 4584",
            reactive_anima_cost=0,
            default_duration_type=DurationType.UNTIL_USED,
        )
        inst = ConditionInstanceFactory(condition=template, target=bearer, absorb_remaining=20)
        payload = _blow(bearer, 5, DamageSource(type="environment", ref=None))

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 0)
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_a_once_only_barrier_drained_dry_ends_through_the_full_teardown(self) -> None:
        bearer, _anima = _bearer()
        template = ConditionTemplateFactory(
            name="Eggshell Bulwark 4584",
            reactive_anima_cost=0,
            default_duration_type=DurationType.UNTIL_USED,
        )
        inst = ConditionInstanceFactory(condition=template, target=bearer, absorb_remaining=10)
        payload = _blow(bearer, 15, DamageSource(type="environment", ref=None))

        with patch.object(
            condition_services,
            "_teardown_removed_condition_instance",
            wraps=condition_services._teardown_removed_condition_instance,
        ) as teardown:
            absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 5)
        teardown.assert_called_once_with(bearer, inst)
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_a_lasting_barrier_with_buffer_left_survives_a_hit(self) -> None:
        bearer, _anima = _bearer()
        template = ConditionTemplateFactory(
            name="Granite Bulwark 4584",
            reactive_anima_cost=0,
            default_duration_type=DurationType.UNTIL_END_OF_COMBAT,
        )
        inst = ConditionInstanceFactory(condition=template, target=bearer, absorb_remaining=20)
        payload = _blow(bearer, 5, DamageSource(type="environment", ref=None))

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 0)
        inst.refresh_from_db()
        self.assertEqual(inst.absorb_remaining, 15)

    def test_a_fizzled_ward_is_not_used(self) -> None:
        bearer, anima = _bearer()
        anima.current = 1
        anima.save(update_fields=["current"])
        inst = ConditionInstanceFactory(
            condition=_ward("Dim Rebuke 4584", REFLECT_DAMAGE_HANDLER_PATH), target=bearer
        )
        payload = _blow(bearer, 20, DamageSource(type="environment", ref=None))

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 20)
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_a_lasting_ward_is_not_spent(self) -> None:
        bearer, _anima = _bearer()
        inst = ConditionInstanceFactory(
            condition=_ward(
                "Steady Rebuke 4584",
                REFLECT_DAMAGE_HANDLER_PATH,
                duration_type=DurationType.UNTIL_END_OF_COMBAT,
            ),
            target=bearer,
        )
        opponent = CombatOpponentFactory(health=50, soak_value=0)
        payload = _blow(bearer, 20, classify_source(opponent))

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())


class OnceOnlyStrikeBackTests(_StrikeBackFixture):
    """Review Focus 1: two hits in one round, one strike-back."""

    def test_a_once_only_strike_back_answers_only_the_first_of_two_hits(self) -> None:
        ward = ConditionTemplateFactory(
            name="Bramble Oath 4584",
            retaliation_damage=5,
            default_duration_type=DurationType.UNTIL_USED,
        )
        result = apply_condition(self.knight_char, ward, source_character=self.caster_char)

        with transaction.atomic():
            apply_damage_to_participant(self.knight_seat, 8, source=self.brute)
            apply_damage_to_participant(self.knight_seat, 8, source=self.brute)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50 - 5)
        self.assertFalse(ConditionInstance.objects.filter(pk=result.instance.pk).exists())

    def test_a_lasting_strike_back_answers_both_hits(self) -> None:
        ward = ConditionTemplateFactory(
            name="Bramble Mantle 4584",
            retaliation_damage=5,
            default_duration_type=DurationType.UNTIL_END_OF_COMBAT,
        )
        apply_condition(self.knight_char, ward, source_character=self.caster_char)

        with transaction.atomic():
            apply_damage_to_participant(self.knight_seat, 8, source=self.brute)
            apply_damage_to_participant(self.knight_seat, 8, source=self.brute)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50 - 10)
