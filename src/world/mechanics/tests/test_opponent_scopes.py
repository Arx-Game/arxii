"""The opponent scopes of a maneuver effect target (#4823)."""

from dataclasses import replace
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.distinctions.factories import DistinctionEffectFactory
from world.magic.factories import GiftFactory, TechniqueFactory
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind, ManeuverEffectKey
from world.mechanics.effect_targets import (
    effect_value,
    opponent_facts,
    opponent_targets_exist,
    technique_effect_context,
    technique_effect_targets,
    technique_effect_total,
)
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
    ObjectPropertyFactory,
    PropertyFactory,
)
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierTarget
from world.mechanics.types import OpponentFacts
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


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


class OpponentFactsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.abyssal = PropertyFactory(name="Facts Abyssal")
        cls.stage_prop = PropertyFactory(name="Facts Stage Mark")
        cls.persona_tag = PropertyFactory(name="Facts Persona Tag")
        cls.bleeding = ConditionTemplateFactory(name="Facts Bleeding")
        cls.cursed = ConditionTemplateFactory(name="Facts Cursed", has_progression=True)
        cls.cursed.properties.add(cls.abyssal)
        cls.cursed_stage = ConditionStageFactory(condition=cls.cursed, stage_order=1)
        cls.cursed_stage.properties.add(cls.stage_prop)

    def setUp(self):
        self.victim = ObjectDBFactory(db_key="Facts Victim")

    def test_nothing_for_no_object(self):
        assert opponent_facts(None) == OpponentFacts()

    def test_an_untouched_object_carries_nothing(self):
        assert opponent_facts(self.victim) == OpponentFacts()

    def test_stored_property(self):
        ObjectPropertyFactory(object=self.victim, property=self.abyssal)
        facts = opponent_facts(self.victim)
        assert facts.property_ids == frozenset({self.abyssal.pk})
        assert facts.condition_ids == frozenset()

    def test_property_granted_by_an_active_condition_template(self):
        ConditionInstanceFactory(target=self.victim, condition=self.cursed)
        facts = opponent_facts(self.victim)
        assert self.abyssal.pk in facts.property_ids
        assert facts.condition_ids == frozenset({self.cursed.pk})

    def test_property_granted_by_the_current_stage(self):
        ConditionInstanceFactory(
            target=self.victim, condition=self.cursed, current_stage=self.cursed_stage
        )
        facts = opponent_facts(self.victim)
        assert facts.property_ids == frozenset({self.abyssal.pk, self.stage_prop.pk})

    def test_a_suppressed_condition_grants_nothing(self):
        ConditionInstanceFactory(
            target=self.victim,
            condition=self.cursed,
            current_stage=self.cursed_stage,
            is_suppressed=True,
        )
        assert opponent_facts(self.victim) == OpponentFacts()

    def test_a_lapsed_suppression_counts_again(self):
        ConditionInstanceFactory(
            target=self.victim,
            condition=self.bleeding,
            is_suppressed=True,
            suppressed_until=timezone.now() - timedelta(minutes=1),
        )
        assert opponent_facts(self.victim).condition_ids == frozenset({self.bleeding.pk})

    def test_condition_ids_list_every_active_condition(self):
        ConditionInstanceFactory(target=self.victim, condition=self.bleeding)
        ConditionInstanceFactory(target=self.victim, condition=self.cursed, is_suppressed=True)
        assert opponent_facts(self.victim).condition_ids == frozenset({self.bleeding.pk})

    def test_a_pcs_primary_persona_tag(self):
        character = CharacterFactory(db_key="Facts Pc")
        sheet = CharacterSheetFactory(character=character)
        sheet.primary_persona.properties.add(self.persona_tag)
        assert opponent_facts(character).property_ids == frozenset({self.persona_tag.pk})

    def test_a_non_primary_persona_tag_does_not_count(self):
        character = CharacterFactory(db_key="Facts Disguised")
        sheet = CharacterSheetFactory(character=character)
        mask = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)
        mask.properties.add(self.persona_tag)
        assert opponent_facts(character).property_ids == frozenset()

    def test_the_query_count_does_not_grow_with_conditions(self):
        ConditionInstanceFactory(target=self.victim, condition=self.cursed)
        with self.assertNumQueries(4):
            opponent_facts(self.victim)
        for n in range(3):
            ConditionInstanceFactory(
                target=self.victim, condition=ConditionTemplateFactory(name=f"Facts Extra {n}")
            )
        with self.assertNumQueries(4):
            opponent_facts(self.victim)


class OpponentReaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_maneuver_effects()
        cls.category = ModifierCategoryFactory(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.character = CharacterFactory(db_key="OpponentReaderChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)
        cls.technique = TechniqueFactory(gift=GiftFactory(name="Opponent Reader Gift"))
        cls.abyssal = PropertyFactory(name="Reader Abyssal")
        cls.bleeding = ConditionTemplateFactory(name="Reader Bleeding")

    def _grant(self, value: int, **scopes) -> ModifierTarget:
        # ModifierTargetFactory looks a target up by name, so each one needs its own.
        target = ModifierTargetFactory(
            category=self.category,
            name=f"Vs opponent {ModifierTarget.objects.count()}",
            scope_effect_kind=EffectKind.DAMAGE,
            **scopes,
        )
        CharacterModifierFactory(
            character=self.sheet,
            target=target,
            value=value,
            source=DistinctionModifierSourceFactory(
                distinction_effect=DistinctionEffectFactory(target=target)
            ),
        )
        return target

    def _total(self, facts: OpponentFacts) -> int:
        context = replace(
            technique_effect_context(self.sheet, self.technique),
            opponent_property_ids=facts.property_ids,
            opponent_condition_ids=facts.condition_ids,
        )
        return technique_effect_total(
            self.sheet, context, technique_effect_targets(EffectKind.DAMAGE)
        )

    def test_a_property_scoped_target_matches_only_that_opponent(self):
        self._grant(5, scope_opponent_property=self.abyssal)
        assert self._total(OpponentFacts(property_ids=frozenset({self.abyssal.pk}))) == 5
        assert self._total(OpponentFacts()) == 0
        assert self._total(OpponentFacts(property_ids=frozenset({self.abyssal.pk + 1000}))) == 0

    def test_a_condition_scoped_target_matches_only_that_opponent(self):
        self._grant(2, scope_opponent_condition=self.bleeding)
        assert self._total(OpponentFacts(condition_ids=frozenset({self.bleeding.pk}))) == 2
        assert self._total(OpponentFacts()) == 0

    def test_a_property_does_not_stand_in_for_a_condition(self):
        self._grant(2, scope_opponent_condition=self.bleeding)
        assert self._total(OpponentFacts(property_ids=frozenset({self.bleeding.pk}))) == 0

    def test_opponent_and_technique_scopes_both_have_to_match(self):
        self._grant(4, scope_gift=self.technique.gift, scope_opponent_property=self.abyssal)
        self._grant(9, scope_gift=GiftFactory(name="Other Reader Gift"))
        facts = OpponentFacts(property_ids=frozenset({self.abyssal.pk}))
        assert self._total(facts) == 4
        assert self._total(OpponentFacts()) == 0

    def test_an_opponent_scoped_target_never_reaches_a_maneuver(self):
        self._grant(5, scope_opponent_property=self.abyssal)
        self._grant(3, scope_opponent_condition=self.bleeding)
        base = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE).base_value
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == base

    def test_opponent_targets_exist(self):
        plain = self._grant(1)
        scoped = self._grant(1, scope_opponent_property=self.abyssal)
        assert not opponent_targets_exist([plain])
        assert opponent_targets_exist([plain, scoped])
        assert not opponent_targets_exist([])
