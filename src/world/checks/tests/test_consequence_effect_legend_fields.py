"""Tests for LEGEND_AWARD effect type fields and clean() validation."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.checks.constants import EffectType
from world.checks.factories import ConsequenceFactory
from world.checks.models import ConsequenceEffect
from world.societies.factories import LegendSourceTypeFactory


class ConsequenceEffectLegendValidationTests(TestCase):
    """Validate that ConsequenceEffect.clean() enforces LEGEND_AWARD field rules."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.consequence = ConsequenceFactory()
        cls.source_type = LegendSourceTypeFactory()

    def _make_effect(self, **kwargs: object) -> ConsequenceEffect:
        return ConsequenceEffect(consequence=self.consequence, **kwargs)

    # ------------------------------------------------------------------
    # LEGEND_AWARD: required field enforcement
    # ------------------------------------------------------------------

    def test_legend_award_requires_base_value(self) -> None:
        effect = self._make_effect(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=None,
            legend_source_type=self.source_type,
        )
        with self.assertRaises(ValidationError) as ctx:
            effect.full_clean()
        self.assertIn("legend_base_value", ctx.exception.message_dict)

    def test_legend_award_requires_positive_base_value(self) -> None:
        effect = self._make_effect(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=0,
            legend_source_type=self.source_type,
        )
        with self.assertRaises(ValidationError) as ctx:
            effect.full_clean()
        self.assertIn("legend_base_value", ctx.exception.message_dict)

    def test_legend_award_requires_source_type(self) -> None:
        effect = self._make_effect(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=10,
            legend_source_type=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            effect.full_clean()
        self.assertIn("legend_source_type", ctx.exception.message_dict)

    def test_legend_award_with_all_required_fields_is_valid(self) -> None:
        effect = self._make_effect(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=5,
            legend_source_type=self.source_type,
            legend_description_template="Awarded for valor in {scene}.",
        )
        # Should not raise
        effect.full_clean()

    def test_legend_description_template_is_optional(self) -> None:
        effect = self._make_effect(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=3,
            legend_source_type=self.source_type,
            legend_description_template="",
        )
        # Should not raise
        effect.full_clean()

    # ------------------------------------------------------------------
    # Non-LEGEND_AWARD types: legend fields must be null/blank
    # ------------------------------------------------------------------

    def test_legend_fields_must_be_null_for_other_types(self) -> None:
        """APPLY_CONDITION with legend_base_value set → ValidationError."""
        from world.conditions.factories import ConditionTemplateFactory

        template = ConditionTemplateFactory()
        effect = self._make_effect(
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=template,
            legend_base_value=5,
        )
        with self.assertRaises(ValidationError) as ctx:
            effect.full_clean()
        self.assertIn("legend_base_value", ctx.exception.message_dict)

    def test_legend_source_type_must_be_null_for_other_types(self) -> None:
        """APPLY_CONDITION with legend_source_type set → ValidationError."""
        from world.conditions.factories import ConditionTemplateFactory

        template = ConditionTemplateFactory()
        effect = self._make_effect(
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=template,
            legend_source_type=self.source_type,
        )
        with self.assertRaises(ValidationError) as ctx:
            effect.full_clean()
        self.assertIn("legend_source_type", ctx.exception.message_dict)

    def test_legend_description_template_must_be_blank_for_other_types(self) -> None:
        """APPLY_CONDITION with non-empty legend_description_template → ValidationError."""
        from world.conditions.factories import ConditionTemplateFactory

        template = ConditionTemplateFactory()
        effect = self._make_effect(
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=template,
            legend_description_template="some text",
        )
        with self.assertRaises(ValidationError) as ctx:
            effect.full_clean()
        self.assertIn("legend_description_template", ctx.exception.message_dict)
