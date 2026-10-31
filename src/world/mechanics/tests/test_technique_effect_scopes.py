"""The technique-side scopes of a maneuver effect target (#4822)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import DamageTypeFactory
from world.distinctions.factories import DistinctionEffectFactory
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind, ManeuverEffectKey
from world.mechanics.effect_targets import (
    effect_modifier_total,
    effect_value,
    technique_effect_context,
    technique_effect_targets,
    technique_effect_total,
)
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
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

    def test_function_only_scope_needs_a_kind(self):
        target = self._build(scope_technique_function=TechniqueFunction.STRIKE)
        self.assertTrue(target.has_technique_scope)
        with self.assertRaises(ValidationError) as ctx:
            target.full_clean()
        self.assertIn("scope_effect_kind", ctx.exception.message_dict)

    def test_constraint_refuses_scope_beside_a_maneuver_effect(self):
        ensure_maneuver_effects()
        effect = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierTarget.objects.create(
                category=self.category,
                name="Effect and gift",
                scope_maneuver_effect=effect,
                scope_effect_kind=EffectKind.DAMAGE,
                scope_gift=self.gift,
            )


class TechniqueEffectReaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_maneuver_effects()
        cls.category = ModifierCategoryFactory(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.character = CharacterFactory(db_key="TechniqueReaderChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)
        cls.fire_gift = GiftFactory(name="Reader Fire")
        cls.child_gift = GiftFactory(name="Reader Ember", parent=cls.fire_gift)
        cls.other_gift = GiftFactory(name="Reader Frost")
        cls.fire_technique = TechniqueFactory(gift=cls.fire_gift)
        cls.ember_technique = TechniqueFactory(gift=cls.child_gift)
        cls.frost_technique = TechniqueFactory(gift=cls.other_gift)
        cls.fire_damage = DamageTypeFactory(name="Reader Fire Damage")
        cls.frost_damage = DamageTypeFactory(name="Reader Frost Damage")

    def _target(self, name, **scopes) -> ModifierTarget:
        scopes.setdefault("scope_effect_kind", EffectKind.DAMAGE)
        return ModifierTargetFactory(category=self.category, name=name, **scopes)

    def _grant(self, target: ModifierTarget, value: int) -> None:
        effect = DistinctionEffectFactory(target=target)
        CharacterModifierFactory(
            character=self.sheet,
            target=target,
            value=value,
            source=DistinctionModifierSourceFactory(distinction_effect=effect),
        )

    def _total(self, technique, *, damage_type_id: int | None = None) -> int:
        context = technique_effect_context(self.sheet, technique, damage_type_id=damage_type_id)
        targets = technique_effect_targets(EffectKind.DAMAGE)
        return technique_effect_total(self.sheet, context, targets)

    def test_unscoped_kind_target_matches_any_technique(self):
        self._grant(self._target("Any damage"), 3)
        assert self._total(self.fire_technique) == 3
        assert self._total(self.frost_technique) == 3

    def test_gift_scope_matches_its_techniques_only(self):
        self._grant(self._target("Fire damage", scope_gift=self.fire_gift), 4)
        assert self._total(self.fire_technique) == 4
        assert self._total(self.frost_technique) == 0

    def test_parent_gift_scope_reaches_child_gift_technique(self):
        self._grant(self._target("Umbrella damage", scope_gift=self.fire_gift), 4)
        assert self._total(self.ember_technique) == 4

    def test_child_gift_scope_does_not_reach_the_parent_gift(self):
        self._grant(self._target("Ember damage", scope_gift=self.child_gift), 4)
        assert self._total(self.fire_technique) == 0

    def test_technique_scope(self):
        self._grant(self._target("One technique", scope_technique=self.fire_technique), 2)
        assert self._total(self.fire_technique) == 2
        assert self._total(self.ember_technique) == 0

    def test_all_set_scopes_must_match(self):
        target = self._target(
            "Fire fire", scope_gift=self.fire_gift, scope_damage_type=self.fire_damage
        )
        self._grant(target, 6)
        assert self._total(self.fire_technique, damage_type_id=self.fire_damage.pk) == 6
        assert self._total(self.fire_technique, damage_type_id=self.frost_damage.pk) == 0
        assert self._total(self.fire_technique) == 0
        assert self._total(self.frost_technique, damage_type_id=self.fire_damage.pk) == 0

    def test_function_scope(self):
        TechniqueFunctionTagFactory(
            technique=self.fire_technique, function=TechniqueFunction.STRIKE
        )
        TechniqueFunctionTagFactory(technique=self.frost_technique, function=TechniqueFunction.MEND)
        target = self._target("Strikes", scope_technique_function=TechniqueFunction.STRIKE)
        self._grant(target, 3)
        assert self._total(self.fire_technique) == 3
        assert self._total(self.frost_technique) == 0

    def test_resonance_scope(self):
        resonance = ResonanceFactory(name="Reader Ember Resonance")
        self.fire_gift.resonances.add(resonance)
        self._grant(self._target("Ember resonant", scope_resonance=resonance), 2)
        assert self._total(self.fire_technique) == 2
        assert self._total(self.frost_technique) == 0

    def test_context_collects_gift_lineage(self):
        context = technique_effect_context(self.sheet, self.ember_technique)
        assert context.technique_id == self.ember_technique.pk
        assert context.gift_ids == frozenset({self.child_gift.pk, self.fire_gift.pk})
        assert context.damage_type_id is None

    def test_technique_targets_exclude_maneuver_effect_rows(self):
        charge = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        kind_only = self._target("Kind only")
        scoped = self._target("Scoped", scope_gift=self.fire_gift)
        self._target("One effect", scope_maneuver_effect=charge, scope_effect_kind="")
        found = technique_effect_targets(EffectKind.DAMAGE)
        assert {t.pk for t in found} == {kind_only.pk, scoped.pk}

    def test_no_sheet_totals_zero(self):
        self._target("Any damage")
        context = technique_effect_context(self.sheet, self.fire_technique)
        targets = technique_effect_targets(EffectKind.DAMAGE)
        assert technique_effect_total(None, context, targets) == 0

    def test_technique_scoped_target_never_reaches_a_maneuver(self):
        self._grant(self._target("Fire damage", scope_gift=self.fire_gift), 5)
        base = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE).base_value
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == base

    def test_kind_wide_false_ignores_kind_targets(self):
        charge = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        self._grant(self._target("Kind wide"), 3)
        self._grant(
            self._target("Charge only", scope_maneuver_effect=charge, scope_effect_kind=""), 2
        )
        key = ManeuverEffectKey.CHARGE_DAMAGE
        assert effect_modifier_total(self.sheet, key, kind_wide=False) == 2
        assert effect_modifier_total(self.sheet, key) == 5
