"""The standoff grade preview counts social contributions the way its roll does (#4594)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane, ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.modifier_models import ModifierTaper
from world.checks.services import collect_check_modifiers
from world.checks.types import ModifierContribution
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.standoffs.services.view import _Grader


class GradePreviewTapersTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory(name="Standoff taper check")
        cls.sheet = CharacterSheetFactory()
        for index in range(3):
            condition = ConditionTemplateFactory(name=f"Steeled {index}")
            ConditionCheckModifierFactory(
                condition=condition, check_type=cls.check_type, modifier_value=10
            )
            ConditionInstanceFactory(target=cls.sheet.character, condition=condition)
        ModifierTaper.objects.create(
            lane=ModifierLane.CHECK,
            source_kind=ModifierSourceKind.CONDITION,
            ratio=Decimal("0.8750"),
            floor=Decimal("0.6667"),
        )

    def test_the_preview_extra_matches_the_rolls_tapered_total(self) -> None:
        social = [
            ModifierContribution(
                source_kind=ModifierSourceKind.CONDITION, source_label="Rallied", value=10
            )
        ]
        rolled = collect_check_modifiers(
            self.sheet, self.check_type, extra_contributions=social
        ).extra_modifiers_total

        with patch(
            "world.standoffs.services.view.preview_check_difficulty", return_value=0
        ) as preview:
            _Grader(sheet=self.sheet).grade(self.check_type, 50, social)

        # Four 10s taper to 10 + 8.75 + 7.66 + 6.70 = 33, not the plain 40.
        self.assertEqual(rolled, 33)
        self.assertEqual(preview.call_args.args[3], rolled)
