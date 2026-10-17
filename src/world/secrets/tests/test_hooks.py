"""Hooks and the truths under them (#4397): the link, its rule, and the shelf that hides a truth."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.constants import SecretProvenance
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.services import (
    SecretError,
    author_truth,
    hooks_for_subject,
    secrets_owned_by,
    truths_by_hook,
)


class TruthUnderAHookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.dreams = SecretFactory(subject_sheet=cls.sheet, content="Dreams that tell.")
        cls.keepsake = SecretFactory(subject_sheet=cls.sheet, content="A keepsake.")

    def test_a_truth_is_unaware_and_hangs_under_its_hook(self):
        truth = author_truth(self.dreams, content="The naga schemer sends them.")
        assert truth.hook_id == self.dreams.pk
        assert truth.subject_aware is False
        assert truth.provenance == SecretProvenance.GM_AUTHORED
        assert truth.subject_sheet_id == self.sheet.pk

    def test_the_subject_keeps_reading_the_hook_only(self):
        author_truth(self.dreams, content="The naga schemer sends them.")
        shelf = list(secrets_owned_by(self.sheet).values_list("content", flat=True))
        assert "Dreams that tell." in shelf
        assert "The naga schemer sends them." not in shelf

    def test_hooks_for_subject_nests_the_truths_and_lists_every_top_level_secret(self):
        truth = author_truth(self.dreams, content="The naga schemer sends them.")
        unaware_hook = SecretFactory(
            subject_sheet=self.sheet, content="Her father was a Tyrant's man.", subject_aware=False
        )
        hooks = list(hooks_for_subject(self.sheet))
        assert [h.pk for h in hooks] == [self.dreams.pk, self.keepsake.pk, unaware_hook.pk]
        grouped = truths_by_hook(self.sheet)
        assert [t.pk for t in grouped[self.dreams.pk]] == [truth.pk]
        assert self.keepsake.pk not in grouped

    def test_a_truth_sits_under_its_own_subjects_hook_only(self):
        from django.core.exceptions import ValidationError

        other = SecretFactory(subject_sheet=CharacterSheetFactory())
        crossed = SecretFactory.build(subject_sheet=self.sheet, hook=other)
        with self.assertRaises(ValidationError):
            crossed.full_clean()

    def test_a_truth_never_has_truths(self):
        truth = author_truth(self.dreams, content="The naga schemer sends them.")
        with self.assertRaises(SecretError):
            author_truth(truth, content="And the schemer is her aunt.")

    def test_a_truth_may_carry_a_category_and_a_level(self):
        magical = SecretCategoryFactory(name="Magical")
        truth = author_truth(self.dreams, content="x", level=3, category=magical)
        assert truth.level == 3
        assert truth.category_id == magical.pk
