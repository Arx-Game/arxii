"""Tests for effect handlers in the mechanics app."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.mechanics.effect_handlers import apply_effect


class MagicalScarsHandlerTests(TestCase):
    """Tests for the MAGICAL_SCARS effect handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory()
        cls.scar_template = ConditionTemplateFactory(
            name="Magical Scars",
            default_duration_type=DurationType.PERMANENT,
        )
        cls.consequence = ConsequenceFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.MAGICAL_SCARS,
            condition_template=cls.scar_template,
        )

    def test_magical_scars_applies_condition(self) -> None:
        """MAGICAL_SCARS handler applies the pointed-to condition template."""
        context = ResolutionContext(character=self.character)
        result = apply_effect(self.effect, context)
        assert result.applied
        assert ConditionInstance.objects.filter(
            target=self.character,
            condition=self.scar_template,
        ).exists()
