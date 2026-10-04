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
