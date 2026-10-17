"""The five lever categories (#4394): the reader, the math, and the seed."""

from django.test import TestCase, override_settings

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import (
    INCOME_CATEGORY_NAME,
    INCOME_TARGET_NAME,
    LEVER_TARGETS,
)
from world.mechanics.levers import lever_total, scale_by_percent
from world.mechanics.models import ModifierCategory, ModifierTarget
from world.mechanics.test_helpers import grant_lever
from world.seeds.levers import ensure_lever_targets


class ScaleByPercentTests(TestCase):
    def test_zero_lever_returns_the_base_untouched(self):
        assert scale_by_percent(100, 0) == 100
        assert scale_by_percent(7, 0, floor=1) == 7

    def test_a_negative_lever_takes_whole_units(self):
        assert scale_by_percent(100, -20) == 80
        assert scale_by_percent(4, -25) == 3

    def test_a_positive_lever_adds(self):
        assert scale_by_percent(100, 25) == 125

    def test_the_floor_holds(self):
        assert scale_by_percent(10, -100, floor=1) == 1
        assert scale_by_percent(10, -200, floor=0) == 0


class LeverTotalTests(TestCase):
    def test_an_unauthored_target_reads_as_zero(self):
        sheet = CharacterSheetFactory()
        assert lever_total(sheet, INCOME_CATEGORY_NAME, INCOME_TARGET_NAME) == 0

    def test_a_distinction_backed_modifier_is_the_total(self):
        sheet = CharacterSheetFactory()
        grant_lever(sheet, INCOME_CATEGORY_NAME, INCOME_TARGET_NAME, -20)
        assert lever_total(sheet, INCOME_CATEGORY_NAME, INCOME_TARGET_NAME) == -20


class EnsureLeverTargetsTests(TestCase):
    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_sample_content_authors_every_lever_once(self):
        ensure_lever_targets()
        ensure_lever_targets()
        names = {(t.category.name, t.name) for t in ModifierTarget.objects.all()}
        assert set(LEVER_TARGETS) <= names
        assert ModifierCategory.objects.filter(name="reputation_gain").count() == 1
        assert ModifierTarget.objects.filter(category__name="reputation_gain").count() == 3

    @override_settings(SEED_SAMPLE_CONTENT=False)
    def test_without_sample_content_nothing_is_invented(self):
        ensure_lever_targets()
        assert not ModifierCategory.objects.filter(name="income").exists()
