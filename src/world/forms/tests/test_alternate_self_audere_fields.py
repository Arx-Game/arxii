"""Constraint and clean() rules for AlternateSelf's Audere fields (#4731)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.forms.constants import AlternateSelfRevertKind
from world.forms.factories import AlternateSelfFactory
from world.forms.models import AlternateSelf


class AlternateSelfAudereFieldsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.behavior = ConditionTemplateFactory(
            category=ConditionCategoryFactory(alters_behavior=True)
        )
        cls.plain = ConditionTemplateFactory(
            category=ConditionCategoryFactory(alters_behavior=False)
        )

    def test_one_flagged_row_per_character(self):
        first = AlternateSelfFactory(emerges_at_audere=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AlternateSelfFactory(character=first.character, emerges_at_audere=True)

    def test_unflagged_rows_unrestricted(self):
        first = AlternateSelfFactory(emerges_at_audere=True)
        AlternateSelfFactory(character=first.character)
        AlternateSelfFactory(character=first.character)

    def test_talked_down_without_condition_fails_clean_and_db(self):
        row = AlternateSelfFactory.build(revert_kind=AlternateSelfRevertKind.TALKED_DOWN)
        with self.assertRaises(ValidationError) as ctx:
            row.clean()
        self.assertIn("emergence_condition", ctx.exception.message_dict)
        with self.assertRaises(IntegrityError) as db_ctx, transaction.atomic():
            AlternateSelfFactory(revert_kind=AlternateSelfRevertKind.TALKED_DOWN)
        self.assertIn("alternate_self_talked_down_needs_condition", str(db_ctx.exception))

    def test_non_behavior_condition_fails_clean(self):
        row = AlternateSelfFactory.build(
            revert_kind=AlternateSelfRevertKind.TALKED_DOWN, emergence_condition=self.plain
        )
        with self.assertRaises(ValidationError) as ctx:
            row.clean()
        self.assertIn("emergence_condition", ctx.exception.message_dict)

    def test_behavior_condition_passes(self):
        row = AlternateSelfFactory(
            revert_kind=AlternateSelfRevertKind.TALKED_DOWN, emergence_condition=self.behavior
        )
        row.clean()
        self.assertEqual(AlternateSelf.objects.get(pk=row.pk).emergence_condition, self.behavior)

    def test_automatic_revert_with_condition_fails_clean(self):
        row = AlternateSelfFactory.build(
            revert_kind=AlternateSelfRevertKind.AUTOMATIC, emergence_condition=self.behavior
        )
        with self.assertRaises(ValidationError) as ctx:
            row.clean()
        self.assertIn("emergence_condition", ctx.exception.message_dict)
