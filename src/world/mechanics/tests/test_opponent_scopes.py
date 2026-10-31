"""The opponent scopes of a maneuver effect target (#4823)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import GiftFactory
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind, ManeuverEffectKey
from world.mechanics.factories import (
    ModifierCategoryFactory,
    ModifierTargetFactory,
    PropertyFactory,
)
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierTarget


class OpponentScopeRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = ModifierCategoryFactory(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.other_category = ModifierCategoryFactory(name="opponent_scope_other")
        cls.abyssal = PropertyFactory(name="Opponent Scope Abyssal")
        cls.bleeding = ConditionTemplateFactory(name="Opponent Scope Bleeding")
        cls.gift = GiftFactory()

    def _build(self, **kwargs) -> ModifierTarget:
        kwargs.setdefault("category", self.category)
        return ModifierTarget(name="Opponent scoped target", **kwargs)

    def test_opponent_scope_needs_a_kind(self):
        target = self._build(scope_opponent_property=self.abyssal)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_effect_kind", ctx.exception.message_dict)

    def test_opponent_condition_scope_needs_a_kind(self):
        target = self._build(scope_opponent_condition=self.bleeding)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_effect_kind", ctx.exception.message_dict)

    def test_opponent_scope_refuses_to_hit(self):
        target = self._build(
            scope_effect_kind=EffectKind.TO_HIT, scope_opponent_property=self.abyssal
        )
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_effect_kind", ctx.exception.message_dict)

    def test_opponent_scope_refuses_a_maneuver_effect(self):
        ensure_maneuver_effects()
        effect = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        target = self._build(scope_maneuver_effect=effect, scope_opponent_property=self.abyssal)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_maneuver_effect", ctx.exception.message_dict)

    def test_other_category_refuses_opponent_scope(self):
        target = self._build(category=self.other_category, scope_opponent_condition=self.bleeding)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_opponent_condition", ctx.exception.message_dict)

    def test_opponent_and_technique_scopes_combine(self):
        target = self._build(
            scope_effect_kind=EffectKind.DAMAGE,
            scope_gift=self.gift,
            scope_opponent_property=self.abyssal,
        )
        target.full_clean()
        self.assertTrue(target.has_opponent_scope)
        self.assertTrue(target.has_technique_scope)

    def test_opponent_scope_alone_is_a_technique_scope_too(self):
        target = self._build(
            scope_effect_kind=EffectKind.CONDITION_SEVERITY,
            scope_opponent_condition=self.bleeding,
        )
        target.full_clean()
        self.assertTrue(target.has_opponent_scope)
        self.assertTrue(target.has_technique_scope)

    def test_technique_scope_alone_is_not_an_opponent_scope(self):
        target = self._build(scope_effect_kind=EffectKind.DAMAGE, scope_gift=self.gift)
        self.assertFalse(target.has_opponent_scope)

    def test_constraint_refuses_opponent_scope_without_kind(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierTargetFactory(
                category=self.category,
                name="Opponent no kind",
                scope_opponent_property=self.abyssal,
            )

    def test_constraint_refuses_opponent_condition_scope_without_kind(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierTargetFactory(
                category=self.category,
                name="Opponent condition no kind",
                scope_opponent_condition=self.bleeding,
            )
