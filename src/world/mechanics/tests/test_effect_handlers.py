"""Tests for effect handlers in the mechanics app."""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.mechanics.effect_handlers import _resolve_target, apply_effect


class ResolveTargetTests(TestCase):
    """Tests for _resolve_target covering SELF, TARGET, and LOCATION."""

    def test_self_returns_context_character(self) -> None:
        effect = MagicMock(target=EffectTarget.SELF)
        character = MagicMock()
        context = MagicMock(character=character)
        assert _resolve_target(effect, context) is character

    def test_target_returns_context_target(self) -> None:
        effect = MagicMock(target=EffectTarget.TARGET)
        target_char = MagicMock()
        context = MagicMock(target=target_char)
        assert _resolve_target(effect, context) is target_char

    def test_target_falls_back_to_character_when_target_is_none(self) -> None:
        effect = MagicMock(target=EffectTarget.TARGET)
        character = MagicMock()
        context = MagicMock(target=None, character=character)
        assert _resolve_target(effect, context) is character


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
