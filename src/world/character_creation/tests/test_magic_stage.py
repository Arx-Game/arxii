"""
Tests for magic stage completion in character creation.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.models import CharacterDraft
from world.magic.factories import (
    DraftAnimaRitualFactory,
    EffectTypeFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceFactory,
    ResonanceModifierTypeFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)


class MagicStageCompletionTest(TestCase):
    """Test magic stage completion logic for character creation."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.resonance = ResonanceModifierTypeFactory()

    def _create_complete_gift(self, draft):
        """Helper to create a gift with affinity, resonance, and 3 techniques."""
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        # Create 3 techniques with required fields
        for i in range(3):
            TechniqueFactory(
                gift=gift,
                style=self.style,
                effect_type=self.effect_type,
                name=f"Technique {i}",
            )
        draft.draft_gifts.add(gift)
        return gift

    def _create_complete_motif(self, draft):
        """Helper to create a motif with at least 1 resonance."""
        motif = MotifFactory(character=None, draft=draft)
        MotifResonanceFactory(motif=motif, resonance=self.resonance)
        return motif

    def _create_complete_anima_ritual(self):
        """Helper to create a complete anima ritual."""
        return DraftAnimaRitualFactory()

    def test_magic_complete_when_skipped(self):
        """Test magic is complete when player hasn't started any magic selection."""
        draft = CharacterDraftFactory(account=self.account)
        # No magic elements created - player skipped the stage
        self.assertTrue(draft._is_magic_complete())

    def test_magic_incomplete_no_gift(self):
        """Test magic is incomplete when motif/ritual started but no gift."""
        draft = CharacterDraftFactory(account=self.account)
        # Create motif and anima ritual but no gift - started but incomplete
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_gift_no_resonance(self):
        """Test magic is incomplete when gift has no resonance."""
        draft = CharacterDraftFactory(account=self.account)
        # Create gift without resonances
        gift = GiftFactory()
        for i in range(3):
            TechniqueFactory(
                gift=gift,
                style=self.style,
                effect_type=self.effect_type,
                name=f"Technique {i}",
            )
        draft.draft_gifts.add(gift)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_techniques(self):
        """Test magic is incomplete when gift has no techniques."""
        draft = CharacterDraftFactory(account=self.account)
        # Create gift without techniques
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        draft.draft_gifts.add(gift)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_not_enough_techniques(self):
        """Test magic is incomplete when gift has fewer than 3 techniques."""
        draft = CharacterDraftFactory(account=self.account)
        # Create gift with only 2 techniques
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        for i in range(2):
            TechniqueFactory(
                gift=gift,
                style=self.style,
                effect_type=self.effect_type,
                name=f"Technique {i}",
            )
        draft.draft_gifts.add(gift)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_technique_missing_name(self):
        """Test magic is incomplete when technique is missing name."""
        draft = CharacterDraftFactory(account=self.account)
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        # Create 2 complete techniques
        for i in range(2):
            TechniqueFactory(
                gift=gift,
                style=self.style,
                effect_type=self.effect_type,
                name=f"Technique {i}",
            )
        # Create 1 technique with empty name
        TechniqueFactory(
            gift=gift,
            style=self.style,
            effect_type=self.effect_type,
            name="",
        )
        draft.draft_gifts.add(gift)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_motif(self):
        """Test magic is incomplete when motif does not exist."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()
        # No motif created

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_motif_no_resonance(self):
        """Test magic is incomplete when motif has no resonances."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        # Create motif without resonances
        MotifFactory(character=None, draft=draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_anima_ritual(self):
        """Test magic is incomplete when anima ritual does not exist."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        # No anima ritual created

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_anima_ritual_missing_description(self):
        """Test magic is incomplete when anima ritual has empty description."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        ritual = DraftAnimaRitualFactory(description="")
        draft.draft_anima_ritual = ritual
        draft.save()

        self.assertFalse(draft._is_magic_complete())

    def test_magic_complete(self):
        """Test magic is complete when all requirements are met."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertTrue(draft._is_magic_complete())

    def test_magic_complete_multiple_gifts(self):
        """Test magic is complete with multiple valid gifts."""
        draft = CharacterDraftFactory(account=self.account)
        # Create two complete gifts
        self._create_complete_gift(draft)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        self.assertTrue(draft._is_magic_complete())

    def test_stage_completion_includes_magic(self):
        """Test that stage_completion includes magic stage."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        draft.draft_anima_ritual = self._create_complete_anima_ritual()
        draft.save()

        stage_completion = draft.get_stage_completion()
        self.assertIn(CharacterDraft.Stage.MAGIC, stage_completion)
        self.assertTrue(stage_completion[CharacterDraft.Stage.MAGIC])
