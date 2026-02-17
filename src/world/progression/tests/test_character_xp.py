"""Tests for CharacterXP models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from evennia.objects.models import ObjectDB
import pytest

from world.progression.models import CharacterXP, CharacterXPTransaction
from world.progression.types import ProgressionReason


class CharacterXPModelTest(TestCase):
    """Test CharacterXP model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TestChar")

    def test_create_locked_xp(self):
        """Test creating locked (non-transferable) XP record."""
        xp = CharacterXP.objects.create(
            character=self.character,
            total_earned=30,
            total_spent=0,
            transferable=False,
        )
        assert xp.current_available == 30
        assert xp.transferable is False

    def test_create_unlocked_xp(self):
        """Test creating unlocked (transferable) XP record."""
        xp = CharacterXP.objects.create(
            character=self.character,
            total_earned=50,
            total_spent=10,
            transferable=True,
        )
        assert xp.current_available == 40
        assert xp.transferable is True

    def test_unique_together_character_transferable(self):
        """Test that character + transferable is unique."""
        CharacterXP.objects.create(
            character=self.character,
            transferable=False,
        )
        with pytest.raises(IntegrityError):
            CharacterXP.objects.create(
                character=self.character,
                transferable=False,
            )

    def test_can_spend(self):
        """Test spending validation."""
        xp = CharacterXP.objects.create(
            character=self.character,
            total_earned=30,
            total_spent=10,
            transferable=False,
        )
        assert xp.can_spend(20)
        assert not xp.can_spend(21)

    def test_spend_xp(self):
        """Test XP spending updates totals."""
        xp = CharacterXP.objects.create(
            character=self.character,
            total_earned=30,
            total_spent=0,
            transferable=False,
        )
        assert xp.spend_xp(10) is True
        assert xp.current_available == 20
        assert xp.total_spent == 10

    def test_spend_xp_insufficient(self):
        """Test spending more than available fails."""
        xp = CharacterXP.objects.create(
            character=self.character,
            total_earned=10,
            total_spent=0,
            transferable=False,
        )
        assert xp.spend_xp(11) is False
        assert xp.current_available == 10

    def test_award_xp(self):
        """Test awarding XP."""
        xp = CharacterXP.objects.create(
            character=self.character,
            total_earned=10,
            transferable=False,
        )
        xp.award_xp(20)
        assert xp.total_earned == 30
        assert xp.current_available == 30

    def test_validation_spent_exceeds_earned(self):
        """Test validation prevents spent exceeding earned."""
        with pytest.raises(ValidationError):
            xp = CharacterXP(
                character=self.character,
                total_earned=5,
                total_spent=10,
                transferable=False,
            )
            xp.full_clean()


class CharacterXPTransactionModelTest(TestCase):
    """Test CharacterXPTransaction model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TestChar2")

    def test_create_cg_conversion_transaction(self):
        """Test creating a CG conversion transaction."""
        txn = CharacterXPTransaction.objects.create(
            character=self.character,
            amount=30,
            reason=ProgressionReason.CG_CONVERSION,
            description="15 unspent CG points converted at 2:1",
            transferable=False,
        )
        assert txn.amount == 30
        assert txn.reason == ProgressionReason.CG_CONVERSION
        assert txn.transferable is False

    def test_transaction_ordering(self):
        """Test transactions are ordered newest first."""
        txn1 = CharacterXPTransaction.objects.create(
            character=self.character,
            amount=10,
            reason=ProgressionReason.CG_CONVERSION,
            transferable=False,
        )
        txn2 = CharacterXPTransaction.objects.create(
            character=self.character,
            amount=20,
            reason=ProgressionReason.SYSTEM_AWARD,
            transferable=True,
        )
        txns = list(CharacterXPTransaction.objects.filter(character=self.character))
        assert txns[0].id == txn2.id
        assert txns[1].id == txn1.id


class AwardCGConversionXPTest(TestCase):
    """Test the CG-to-XP conversion service function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="ConvertChar")

    def test_awards_correct_xp(self):
        """Test conversion awards remaining * rate XP."""
        from world.progression.services import award_cg_conversion_xp

        award_cg_conversion_xp(self.character, remaining_cg_points=15, conversion_rate=2)

        xp = CharacterXP.objects.get(character=self.character, transferable=False)
        assert xp.total_earned == 30
        assert xp.current_available == 30

    def test_creates_transaction(self):
        """Test conversion creates audit trail transaction."""
        from world.progression.services import award_cg_conversion_xp

        award_cg_conversion_xp(self.character, remaining_cg_points=10, conversion_rate=2)

        txn = CharacterXPTransaction.objects.get(character=self.character)
        assert txn.amount == 20
        assert txn.reason == ProgressionReason.CG_CONVERSION
        assert txn.transferable is False

    def test_skips_zero_remaining(self):
        """Test no XP or transaction created when remaining is 0."""
        from world.progression.services import award_cg_conversion_xp

        award_cg_conversion_xp(self.character, remaining_cg_points=0, conversion_rate=2)

        assert not CharacterXP.objects.filter(character=self.character).exists()
        assert not CharacterXPTransaction.objects.filter(character=self.character).exists()

    def test_skips_negative_remaining(self):
        """Test no XP created when remaining is negative (should not happen)."""
        from world.progression.services import award_cg_conversion_xp

        award_cg_conversion_xp(self.character, remaining_cg_points=-5, conversion_rate=2)

        assert not CharacterXP.objects.filter(character=self.character).exists()

    def test_custom_conversion_rate(self):
        """Test conversion with non-default rate."""
        from world.progression.services import award_cg_conversion_xp

        award_cg_conversion_xp(self.character, remaining_cg_points=10, conversion_rate=3)

        xp = CharacterXP.objects.get(character=self.character, transferable=False)
        assert xp.total_earned == 30
