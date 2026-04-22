"""Tests for effect handlers in the mechanics app."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.conditions.factories import DamageTypeFactory
from world.mechanics.effect_handlers import _resolve_target, apply_effect
from world.vitals.models import CharacterVitals


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
    """Tests for the MAGICAL_SCARS effect handler.

    The handler now creates a PendingAlteration rather than directly applying
    a condition. Full coverage lives in world.magic.tests.test_alteration_handler.
    This suite covers the skip paths exercised via the mechanics test DB.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Character with no CharacterSheet — exercises the skip path.
        cls.character = CharacterFactory()
        cls.consequence = ConsequenceFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.MAGICAL_SCARS,
        )

    def test_magical_scars_skips_without_sheet(self) -> None:
        """MAGICAL_SCARS handler returns applied=False when target has no CharacterSheet."""
        context = ResolutionContext(character=self.character)
        result = apply_effect(self.effect, context)
        assert not result.applied
        assert result.skip_reason is not None


class DealDamageHandlerTests(TestCase):
    """Tests for the DEAL_DAMAGE effect handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory(db_key="damage_target")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.vitals = CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=100,
            max_health=100,
        )
        cls.damage_type = DamageTypeFactory(name="fire")
        cls.consequence = ConsequenceFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=30,
            damage_type=cls.damage_type,
        )

    def setUp(self) -> None:
        """Reset vitals health before each test."""
        CharacterVitals.objects.filter(pk=self.vitals.pk).update(health=100)
        self.vitals.refresh_from_db()

    @patch("world.mechanics.effect_handlers.process_damage_consequences")
    def test_applies_damage_to_vitals(self, mock_pipeline: MagicMock) -> None:
        """DEAL_DAMAGE handler reduces health on CharacterVitals."""
        context = ResolutionContext(character=self.character)
        result = apply_effect(self.effect, context)
        self.vitals.refresh_from_db()
        assert result.applied is True
        assert self.vitals.health == 70
        mock_pipeline.assert_called_once_with(
            character=self.character,
            damage_dealt=30,
            damage_type=self.damage_type,
        )

    def test_returns_applied_true_with_description(self) -> None:
        """Successful damage returns applied=True with a descriptive message."""
        with patch("world.mechanics.effect_handlers.process_damage_consequences"):
            context = ResolutionContext(character=self.character)
            result = apply_effect(self.effect, context)
        assert result.applied is True
        assert "30" in result.description
        assert "fire" in result.description
        assert result.effect_type == EffectType.DEAL_DAMAGE

    def test_skips_when_no_vitals(self) -> None:
        """Target without vitals gets applied=False."""
        char_no_vitals = CharacterFactory(db_key="no_vitals_char")
        CharacterSheetFactory(character=char_no_vitals)
        # No CharacterVitals created for this character
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=10,
            damage_type=self.damage_type,
        )
        context = ResolutionContext(character=char_no_vitals)
        result = apply_effect(effect, context)
        assert result.applied is False
        assert "no charactervitals" in result.skip_reason.lower()

    def test_skips_when_no_sheet(self) -> None:
        """Target without a CharacterSheet gets applied=False."""
        char_no_sheet = CharacterFactory(db_key="no_sheet_char")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=10,
            damage_type=self.damage_type,
        )
        context = ResolutionContext(character=char_no_sheet)
        result = apply_effect(effect, context)
        assert result.applied is False
