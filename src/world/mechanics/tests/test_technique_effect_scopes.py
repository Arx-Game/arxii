"""The technique-side scopes of a maneuver effect target (#4822)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import DamageTypeFactory
from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind, ManeuverEffectKey
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierTarget


class TechniqueScopeRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = ModifierCategoryFactory(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.other_category = ModifierCategoryFactory(name="technique_scope_other")
        cls.technique = TechniqueFactory()
        cls.gift = GiftFactory()
        cls.damage_type = DamageTypeFactory()
        cls.resonance = ResonanceFactory()

    def _build(self, **kwargs) -> ModifierTarget:
        kwargs.setdefault("category", self.category)
        return ModifierTarget(name="Scoped target", **kwargs)

    def test_technique_scope_needs_a_kind(self):
        target = self._build(scope_technique=self.technique)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_effect_kind", ctx.exception.message_dict)

    def test_technique_scope_refuses_a_maneuver_effect(self):
        ensure_maneuver_effects()
        effect = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        target = self._build(scope_maneuver_effect=effect, scope_gift=self.gift)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_maneuver_effect", ctx.exception.message_dict)

    def test_damage_type_scope_is_damage_only(self):
        target = self._build(
            scope_effect_kind=EffectKind.CONDITION_SEVERITY,
            scope_damage_type=self.damage_type,
        )
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_damage_type", ctx.exception.message_dict)

    def test_scopes_combine(self):
        target = self._build(
            scope_effect_kind=EffectKind.DAMAGE,
            scope_gift=self.gift,
            scope_damage_type=self.damage_type,
        )
        target.full_clean()
        self.assertTrue(target.has_technique_scope)

    def test_no_technique_scope_reads_false(self):
        target = self._build(scope_effect_kind=EffectKind.DAMAGE)
        self.assertFalse(target.has_technique_scope)

    def test_other_category_refuses_technique_scope(self):
        target = self._build(category=self.other_category, scope_resonance=self.resonance)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_resonance", ctx.exception.message_dict)

    def test_constraint_refuses_scope_without_kind(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierTargetFactory(
                category=self.category,
                name="No kind",
                scope_technique=self.technique,
            )
