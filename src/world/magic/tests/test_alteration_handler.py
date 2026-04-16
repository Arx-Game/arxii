"""Tests for the rewritten _apply_magical_scars effect handler."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.magic.constants import PendingAlterationStatus
from world.magic.factories import AffinityFactory, CharacterResonanceFactory, ResonanceFactory
from world.magic.models import PendingAlteration
from world.mechanics.effect_handlers import apply_effect


class ApplyMagicalScarsHandlerTests(TestCase):
    """Test _apply_magical_scars handler creates PendingAlteration."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)
        cls.sheet = CharacterSheetFactory()
        # Give the character an active resonance so origin can be derived.
        cls.char_resonance = CharacterResonanceFactory(
            character=cls.sheet.character,
            resonance=cls.resonance,
            is_active=True,
        )

    def _make_effect(self, severity=1):
        """Create a mock ConsequenceEffect with MAGICAL_SCARS type."""
        consequence = ConsequenceFactory()
        return ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.MAGICAL_SCARS,
            condition_severity=severity,
        )

    def _make_context(self):
        """Create a ResolutionContext pointing at the test character."""
        return ResolutionContext(character=self.sheet.character)

    def test_handler_creates_pending_alteration(self):
        """MAGICAL_SCARS handler creates a PendingAlteration, not a direct condition."""
        effect = self._make_effect(severity=2)
        context = self._make_context()
        result = apply_effect(effect, context)
        assert result.applied is True
        assert PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).exists()

    def test_handler_does_not_apply_condition_directly(self):
        """Handler should NOT create any ConditionInstance directly."""
        from world.conditions.models import ConditionInstance

        effect = self._make_effect(severity=1)
        context = self._make_context()
        initial_count = ConditionInstance.objects.count()
        apply_effect(effect, context)
        assert ConditionInstance.objects.count() == initial_count

    def test_pending_alteration_origin_from_character_resonance(self):
        """Origin affinity and resonance are derived from the character's active resonance."""
        effect = self._make_effect(severity=1)
        context = self._make_context()
        apply_effect(effect, context)
        pending = PendingAlteration.objects.get(character=self.sheet)
        assert pending.origin_affinity == self.affinity
        assert pending.origin_resonance == self.resonance

    def test_severity_maps_to_tier(self):
        """condition_severity on the effect determines the pending tier."""
        effect = self._make_effect(severity=3)
        context = self._make_context()
        apply_effect(effect, context)
        pending = PendingAlteration.objects.filter(character=self.sheet).order_by("-pk").first()
        assert pending is not None
        assert pending.tier == 3

    def test_handler_skips_when_no_character_sheet(self):
        """Handler returns applied=False when target has no CharacterSheet."""
        effect = self._make_effect(severity=1)
        bare_character = MagicMock()
        # Simulate missing sheet_data (DoesNotExist raises AttributeError via descriptor)
        del bare_character.sheet_data
        context = ResolutionContext(character=bare_character)
        result = apply_effect(effect, context)
        assert result.applied is False

    def test_handler_skips_when_no_resonance(self):
        """Handler returns applied=False when character has no active resonance."""
        sheet_no_res = CharacterSheetFactory()
        # No CharacterResonance created for this sheet's character
        effect = self._make_effect(severity=1)
        context = ResolutionContext(character=sheet_no_res.character)
        result = apply_effect(effect, context)
        assert result.applied is False
