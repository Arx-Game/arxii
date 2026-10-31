"""The aspect lever (#4827): a distinction's +N on an Aspect reaches the checks that weight it."""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeAspectFactory, CheckTypeFactory
from world.checks.services import collect_check_modifiers
from world.classes.factories import AspectFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.services import create_distinction_modifiers, ensure_aspect_target


class AspectLeverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diplomacy = AspectFactory(name="Diplomacy")
        cls.target = ensure_aspect_target(cls.diplomacy)
        cls.parley = CheckTypeFactory(name="Parley (aspect lever)")
        CheckTypeAspectFactory(check_type=cls.parley, aspect=cls.diplomacy, weight=Decimal("1.0"))
        cls.haggle = CheckTypeFactory(name="Haggle (aspect lever)")
        CheckTypeAspectFactory(check_type=cls.haggle, aspect=cls.diplomacy, weight=Decimal("0.5"))
        cls.climb = CheckTypeFactory(name="Climb (aspect lever)")
        cls.whisper = DistinctionFactory(
            name="Whisper", slug="whisper-aspect-lever", cost_per_rank=0
        )
        DistinctionEffectFactory(distinction=cls.whisper, target=cls.target, value_per_rank=10)

    def setUp(self):
        self.character = ObjectDBFactory(db_key="AspectLeverHolder")
        self.sheet = CharacterSheetFactory(character=self.character)

    def take_whisper(self) -> None:
        held = CharacterDistinctionFactory(character=self.sheet, distinction=self.whisper)
        create_distinction_modifiers(held)

    def test_a_full_weight_check_takes_the_whole_bonus_named_for_the_aspect(self):
        self.take_whisper()
        breakdown = collect_check_modifiers(self.sheet, self.parley)
        (row,) = [c for c in breakdown.contributions if "Diplomacy" in c.source_label]
        assert (row.source_kind, row.value) == (ModifierSourceKind.CHARACTER, 10)
        assert row.source_label == "Whisper (Diplomacy)"
        assert breakdown.total == 10

    def test_a_half_weight_check_takes_half(self):
        self.take_whisper()
        assert collect_check_modifiers(self.sheet, self.haggle).total == 5

    def test_a_check_that_does_not_weight_the_aspect_is_unchanged(self):
        self.take_whisper()
        assert collect_check_modifiers(self.sheet, self.climb).total == 0

    def test_without_the_card_nothing_is_added(self):
        assert collect_check_modifiers(self.sheet, self.parley).total == 0

    def test_an_inactive_target_is_skipped(self):
        self.take_whisper()
        self.target.is_active = False
        self.target.save()
        try:
            assert collect_check_modifiers(self.sheet, self.parley).total == 0
        finally:
            self.target.is_active = True
            self.target.save()
