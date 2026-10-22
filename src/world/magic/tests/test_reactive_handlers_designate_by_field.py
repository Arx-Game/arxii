"""absorb_pool / reflect_damage find their condition by field, not by name (#4572).

A barrier or reflect condition staff name anything else must still work; the
shipped "Aegis Field" / "Mirror Ward" rows are just the default spelling.

* ``absorb_pool`` designates any active instance of the bearer holding a buffer
  (``absorb_remaining > 0``).
* ``reflect_damage`` designates an instance whose template carries a reactive
  trigger whose flow calls the handler, the same data ``protective_flavor`` reads.
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
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.damage_source import classify_source
from world.combat.factories import CombatOpponentFactory
from world.conditions.constants import FORCE_FIELD_CONDITION_NAME, REFLECT_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.effect_palette_content import ensure_force_field_content, ensure_reflect_content
from world.magic.factories import CharacterAnimaFactory
from world.magic.services.effect_handlers import (
    REFLECT_DAMAGE_HANDLER_PATH,
    absorb_pool,
    reflect_damage,
)


def _bearer():
    bearer = CharacterSheetFactory().character
    anima = CharacterAnimaFactory(character=bearer.sheet_data, current=10, maximum=10)
    return bearer, anima


def _reflect_template(name: str):
    """A reflect ward called *name*: a template whose trigger flow calls reflect_damage."""
    template = ConditionTemplateFactory(name=name, reactive_anima_cost=2)
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name=REFLECT_DAMAGE_HANDLER_PATH,
    )
    template.reactive_triggers.add(
        TriggerDefinitionFactory(flow_definition=flow, event_name=EventName.DAMAGE_PRE_APPLY)
    )
    return template


class AbsorbPoolDesignatesByBufferTests(TestCase):
    def test_barrier_with_a_different_name_still_absorbs(self) -> None:
        bearer, anima = _bearer()
        template = ConditionTemplateFactory(name="Moonlit Bulwark", reactive_anima_cost=1)
        instance = ConditionInstanceFactory(condition=template, target=bearer, absorb_remaining=20)
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=15,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 0)
        instance.refresh_from_db()
        self.assertEqual(instance.absorb_remaining, 5)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 9)

    def test_shipped_aegis_field_still_absorbs(self) -> None:
        bearer, _anima = _bearer()
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        instance = ConditionInstanceFactory(condition=template, target=bearer, absorb_remaining=20)
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=8,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 0)
        instance.refresh_from_db()
        self.assertLess(instance.absorb_remaining, 20)

    def test_oldest_buffer_drains_first_regardless_of_name(self) -> None:
        bearer, _anima = _bearer()
        older = ConditionInstanceFactory(
            condition=ConditionTemplateFactory(name="Older Veil", reactive_anima_cost=0),
            target=bearer,
            absorb_remaining=10,
        )
        newer = ConditionInstanceFactory(
            condition=ConditionTemplateFactory(name=FORCE_FIELD_CONDITION_NAME),
            target=bearer,
            absorb_remaining=10,
        )
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=4,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )

        absorb_pool(payload=payload)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(older.absorb_remaining, 6)
        self.assertEqual(newer.absorb_remaining, 10)

    def test_resolved_or_empty_buffers_are_ignored(self) -> None:
        bearer, _anima = _bearer()
        template = ConditionTemplateFactory(name="Spent Veil", reactive_anima_cost=0)
        ConditionInstanceFactory(condition=template, target=bearer, absorb_remaining=0)
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=9,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )

        absorb_pool(payload=payload)

        self.assertEqual(payload.amount, 9)
        self.assertEqual(ConditionInstance.objects.filter(target=bearer).count(), 1)


class ReflectDamageDesignatesByTriggerTests(TestCase):
    def test_reflect_ward_with_a_different_name_still_reflects(self) -> None:
        bearer, anima = _bearer()
        ConditionInstanceFactory(condition=_reflect_template("Silver Rebuke"), target=bearer)
        opponent = CombatOpponentFactory(health=50, soak_value=0)
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 8)

    def test_shipped_mirror_ward_still_reflects(self) -> None:
        bearer, _anima = _bearer()
        ensure_reflect_content()
        template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)
        ConditionInstanceFactory(condition=template, target=bearer)
        opponent = CombatOpponentFactory(health=50, soak_value=0)
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)

    def test_template_named_mirror_ward_without_the_trigger_does_not_reflect(self) -> None:
        """The name alone no longer designates a reflect ward."""
        bearer, anima = _bearer()
        template = ConditionTemplateFactory(name=REFLECT_CONDITION_NAME, reactive_anima_cost=2)
        ConditionInstanceFactory(condition=template, target=bearer)
        opponent = CombatOpponentFactory(health=50, soak_value=0)
        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 20)
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 50)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 10)
