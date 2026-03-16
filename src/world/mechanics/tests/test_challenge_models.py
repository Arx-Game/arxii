"""Tests for Challenge and Situation models."""

from django.db import IntegrityError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.mechanics.constants import ChallengeType, DiscoveryType
from world.mechanics.factories import (
    ApplicationFactory,
    ApproachConsequenceFactory,
    ChallengeApproachFactory,
    ChallengeCategoryFactory,
    ChallengeConsequenceFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
    SituationChallengeLinkFactory,
    SituationTemplateFactory,
)
from world.mechanics.models import (
    ChallengeCategory,
    ChallengeInstance,
    ChallengeTemplate,
    CharacterChallengeRecord,
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
