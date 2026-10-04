"""Model tests for standoffs."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, tag

from world.combat.factories import CreatureTemplateFactory
from world.mechanics.factories import PropertyFactory
from world.standoffs.constants import RevealKind
from world.standoffs.factories import (
    CreatureDriveFactory,
    RegardRuleFactory,
    StandoffApproachFactory,
    StandoffGroupFactory,
    StandoffRevealFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffConfig, StandoffReveal


class StandoffModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = CreatureTemplateFactory()
        cls.group = StandoffGroupFactory(creature_template=cls.template)

    def test_factories_create_every_model(self) -> None:
        for obj in (
            CreatureDriveFactory(),
            RegardRuleFactory(),
            StandoffApproachFactory(),
            StandoffTermsFactory(),
            self.group,
            StandoffRevealFactory(),
        ):
            self.assertTrue(obj.pk)
            self.assertTrue(str(obj))

    def test_drive_reveal_requires_drive(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            StandoffReveal.objects.create(group=self.group, kind=RevealKind.DRIVE)

    def test_drive_reveal_with_drive_is_valid(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template)
        reveal = StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=drive)
        self.assertEqual(reveal.drive, drive)

    @tag("postgres")  # nulls_distinct=False is unenforced on SQLite
    def test_duplicate_cause_reveal_rejected(self) -> None:
        StandoffRevealFactory(group=self.group)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StandoffReveal.objects.create(group=self.group, kind=RevealKind.CAUSE)

    def test_config_load_returns_same_row(self) -> None:
        self.assertEqual(StandoffConfig.load().pk, StandoffConfig.load().pk)
        self.assertEqual(StandoffConfig.objects.count(), 1)

    def test_drive_unique_per_template_property(self) -> None:
        prop = PropertyFactory()
        CreatureDriveFactory(creature_template=self.template, property=prop)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CreatureDriveFactory(creature_template=self.template, property=prop)

    def test_regard_rule_clean_rejects_bad_tree(self) -> None:
        rule = RegardRuleFactory(creature_template=self.template, rule={"op": "nonsense"})
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_regard_rule_drive_must_be_one_of_the_templates_drives(self) -> None:
        stranger = PropertyFactory()
        rule = RegardRuleFactory(creature_template=self.template, drive=stranger)
        with self.assertRaises(ValidationError) as caught:
            rule.clean()
        self.assertIn("drive", caught.exception.message_dict)

    def test_regard_rule_drive_on_a_template_drive_is_valid(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template)
        rule = RegardRuleFactory(creature_template=self.template, drive=drive.property)
        rule.clean()

    def test_cause_margin_must_stay_above_minus_one_hundred(self) -> None:
        template = CreatureTemplateFactory.build(cause_margin_percent=-100)
        with self.assertRaises(ValidationError) as caught:
            template.clean_fields(exclude=["tier", "threat_pool"])
        self.assertIn("cause_margin_percent", caught.exception.message_dict)
        template.cause_margin_percent = -99
        template.clean_fields(exclude=["tier", "threat_pool"])

    def test_deleting_a_creature_template_deletes_its_groups(self) -> None:
        group = StandoffGroupFactory()
        group.creature_template.delete()
        self.assertFalse(StandoffGroupFactory._meta.model.objects.filter(pk=group.pk).exists())
