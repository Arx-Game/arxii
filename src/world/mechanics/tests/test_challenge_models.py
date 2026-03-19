"""Tests for Challenge and Situation models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import ConditionTemplateFactory, DamageTypeFactory
from world.mechanics.constants import ChallengeType, DiscoveryType, EffectType
from world.mechanics.factories import (
    ApplicationFactory,
    ApproachConsequenceFactory,
    ChallengeApproachFactory,
    ChallengeCategoryFactory,
    ChallengeConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    ConsequenceEffectFactory,
    ObjectPropertyFactory,
    PropertyFactory,
    SituationChallengeLinkFactory,
    SituationTemplateFactory,
)
from world.mechanics.models import (
    ChallengeCategory,
    ChallengeInstance,
    ChallengeTemplate,
    ChallengeTemplateProperty,
    CharacterChallengeRecord,
    ConsequenceEffect,
    ObjectProperty,
    SituationInstance,
    SituationTemplate,
)


class ChallengeCategoryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = ChallengeCategoryFactory(name="Environmental")

    def test_str(self) -> None:
        self.assertEqual(str(self.category), "Environmental")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            ChallengeCategory.objects.create(name="Environmental")


class ChallengeTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ChallengeTemplateFactory(name="Locked Door")
        cls.prop = PropertyFactory(name="locked")

    def test_str(self) -> None:
        self.assertEqual(str(self.template), "Locked Door")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            ChallengeTemplate.objects.create(name="Locked Door", category=self.template.category)

    def test_properties_m2m(self) -> None:
        self.template.properties.add(self.prop)
        self.assertIn(self.prop, self.template.properties.all())

    def test_defaults(self) -> None:
        self.assertEqual(self.template.challenge_type, ChallengeType.INHIBITOR)
        self.assertEqual(self.template.severity, 1)
        self.assertEqual(self.template.discovery_type, DiscoveryType.OBVIOUS)
        self.assertIsNone(self.template.blocked_capability)


class ChallengeConsequenceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.consequence = ChallengeConsequenceFactory(label="Door shatters")

    def test_str_contains_label(self) -> None:
        self.assertIn("Door shatters", str(self.consequence))

    def test_defaults(self) -> None:
        self.assertEqual(self.consequence.weight, 1)
        self.assertFalse(self.consequence.character_loss)

    def test_unique_label_per_template(self) -> None:
        with self.assertRaises(IntegrityError):
            ChallengeConsequenceFactory(
                challenge_template=self.consequence.challenge_template,
                label="Door shatters",
            )


class ChallengeApproachTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.application = ApplicationFactory(name="Lockpick")
        cls.approach_with_name = ChallengeApproachFactory(
            display_name="Pick the Lock",
            application=cls.application,
        )
        cls.approach_without_name = ChallengeApproachFactory(
            display_name="",
            application=ApplicationFactory(name="Bash"),
        )
        cls.effect_prop = PropertyFactory(name="fire")

    def test_str_with_display_name(self) -> None:
        self.assertEqual(str(self.approach_with_name), "Pick the Lock")

    def test_str_without_display_name(self) -> None:
        self.assertEqual(str(self.approach_without_name), "Bash")

    def test_unique_application_per_template(self) -> None:
        with self.assertRaises(IntegrityError):
            ChallengeApproachFactory(
                challenge_template=self.approach_with_name.challenge_template,
                application=self.application,
            )

    def test_required_effect_property(self) -> None:
        approach = ChallengeApproachFactory(required_effect_property=self.effect_prop)
        self.assertEqual(approach.required_effect_property, self.effect_prop)


class ApproachConsequenceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.consequence = ApproachConsequenceFactory(label="Lock melts")

    def test_str_contains_label(self) -> None:
        self.assertIn("Lock melts", str(self.consequence))

    def test_nullable_overrides(self) -> None:
        consequence = ApproachConsequenceFactory(
            weight=None,
            mechanical_description="",
            resolution_type="",
        )
        self.assertIsNone(consequence.weight)
        self.assertEqual(consequence.mechanical_description, "")
        self.assertEqual(consequence.resolution_type, "")


class SituationTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = SituationTemplateFactory(name="Burning Building")

    def test_str(self) -> None:
        self.assertEqual(str(self.template), "Burning Building")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            SituationTemplate.objects.create(
                name="Burning Building", category=self.template.category
            )


class SituationChallengeLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.situation = SituationTemplateFactory(name="Dungeon")
        cls.challenge = ChallengeTemplateFactory(name="Trap")
        cls.link = SituationChallengeLinkFactory(
            situation_template=cls.situation,
            challenge_template=cls.challenge,
        )

    def test_str(self) -> None:
        self.assertEqual(str(self.link), "Dungeon → Trap")

    def test_challenges_through_m2m(self) -> None:
        self.assertIn(self.challenge, self.situation.challenges.all())

    def test_dependency(self) -> None:
        challenge2 = ChallengeTemplateFactory(name="Boss")
        link2 = SituationChallengeLinkFactory(
            situation_template=self.situation,
            challenge_template=challenge2,
            depends_on=self.link,
        )
        self.assertEqual(link2.depends_on, self.link)

    def test_unique_situation_challenge(self) -> None:
        with self.assertRaises(IntegrityError):
            SituationChallengeLinkFactory(
                situation_template=self.situation,
                challenge_template=self.challenge,
            )


class InstanceModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDB.objects.create(db_key="Test Room")
        cls.character = ObjectDB.objects.create(db_key="Test Character")
        cls.situation_template = SituationTemplateFactory(name="Siege")
        cls.challenge_template = ChallengeTemplateFactory(name="Barricade")
        cls.situation_instance = SituationInstance.objects.create(
            template=cls.situation_template,
            location=cls.room,
        )
        cls.challenge_instance = ChallengeInstance.objects.create(
            situation_instance=cls.situation_instance,
            template=cls.challenge_template,
            location=cls.room,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.challenge_template,
        )

    def test_situation_instance_str(self) -> None:
        self.assertEqual(str(self.situation_instance), "Siege at Test Room")

    def test_challenge_instance_str(self) -> None:
        self.assertEqual(str(self.challenge_instance), "Barricade at Test Room")

    def test_challenge_instance_standalone(self) -> None:
        standalone = ChallengeInstance.objects.create(
            situation_instance=None,
            template=self.challenge_template,
            location=self.room,
        )
        self.assertIsNone(standalone.situation_instance)
        self.assertTrue(standalone.is_active)

    def test_character_challenge_record(self) -> None:
        record = CharacterChallengeRecord.objects.create(
            character=self.character,
            challenge_instance=self.challenge_instance,
            approach=self.approach,
        )
        self.assertIsNotNone(record.resolved_at)

    def test_character_challenge_record_unique(self) -> None:
        CharacterChallengeRecord.objects.create(
            character=self.character,
            challenge_instance=self.challenge_instance,
            approach=self.approach,
        )
        with self.assertRaises(IntegrityError):
            CharacterChallengeRecord.objects.create(
                character=self.character,
                challenge_instance=self.challenge_instance,
                approach=self.approach,
            )


class ChallengeTemplatePropertyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ctp = ChallengeTemplatePropertyFactory(
            challenge_template=ChallengeTemplateFactory(name="Frozen Gate"),
            property=PropertyFactory(name="frozen"),
        )

    def test_str(self) -> None:
        self.assertEqual(str(self.ctp), "Frozen Gate: frozen (1)")

    def test_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            ChallengeTemplateProperty.objects.create(
                challenge_template=self.ctp.challenge_template,
                property=self.ctp.property,
            )

    def test_default_value(self) -> None:
        ctp = ChallengeTemplatePropertyFactory()
        self.assertEqual(ctp.value, 1)


class ObjectPropertyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.obj = ObjectDB.objects.create(db_key="Iron Door")
        cls.prop = PropertyFactory(name="rusty")
        cls.op = ObjectPropertyFactory(object=cls.obj, property=cls.prop)

    def test_str(self) -> None:
        self.assertEqual(str(self.op), "Iron Door: rusty (1)")

    def test_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            ObjectProperty.objects.create(object=self.obj, property=self.prop)

    def test_source_fks_nullable(self) -> None:
        self.assertIsNone(self.op.source_condition)
        self.assertIsNone(self.op.source_challenge)


class ConsequenceEffectTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.condition_template = ConditionTemplateFactory(name="Burning")
        cls.damage_type = DamageTypeFactory(name="Fire")
        cls.prop = PropertyFactory(name="scorched")

    def test_str(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.APPLY_CONDITION)
        self.assertEqual(
            str(effect),
            f"{effect.consequence.label}: Apply Condition",
        )

    def test_ordering(self) -> None:
        consequence = ChallengeConsequenceFactory(label="Explosion")
        effect_b = ConsequenceEffectFactory(
            consequence=consequence, execution_order=2, effect_type=EffectType.ADD_PROPERTY
        )
        effect_a = ConsequenceEffectFactory(
            consequence=consequence, execution_order=1, effect_type=EffectType.APPLY_CONDITION
        )
        effects = list(ConsequenceEffect.objects.filter(consequence=consequence))
        self.assertEqual(effects, [effect_a, effect_b])

    def test_clean_apply_condition_requires_template(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.APPLY_CONDITION)
        effect.condition_template = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_remove_condition_requires_template(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.REMOVE_CONDITION)
        effect.condition_template = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_add_property_requires_property(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.ADD_PROPERTY)
        effect.property = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_remove_property_requires_property(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.REMOVE_PROPERTY)
        effect.property = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_deal_damage_requires_amount_and_type(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.DEAL_DAMAGE)
        effect.damage_amount = None
        effect.damage_type = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_launch_flow_requires_definition(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.LAUNCH_FLOW)
        effect.flow_definition = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_grant_codex_requires_entry(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.GRANT_CODEX)
        effect.codex_entry = None
        with self.assertRaises(ValidationError):
            effect.full_clean()

    def test_clean_valid_apply_condition_passes(self) -> None:
        effect = ConsequenceEffectFactory(
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=self.condition_template,
        )
        # Should not raise
        effect.full_clean()
