"""
Tests for Random Scene models.
"""

import datetime

from django.db import IntegrityError
from django.test import TestCase
import pytest

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.progression.models import RandomSceneCompletion, RandomSceneTarget


class RandomSceneTargetModelTest(TestCase):
    """Test RandomSceneTarget model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rs_player")
        cls.target_char = ObjectDBFactory(db_key="target_char")
        cls.week_start = datetime.date(2026, 3, 23)  # A Monday

    def setUp(self) -> None:
        RandomSceneTarget.flush_instance_cache()

    def test_create_with_all_fields(self) -> None:
        """Target can be created with all fields."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
            claimed=True,
            first_time=True,
            rerolled=True,
        )
        assert target.pk is not None
        assert target.account == self.account
        assert target.target_character == self.target_char
        assert target.week_start == self.week_start
        assert target.slot_number == 1
        assert target.claimed is True
        assert target.first_time is True
        assert target.rerolled is True

    def test_default_values(self) -> None:
        """Defaults are claimed=False, first_time=False, rerolled=False."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
        )
        assert target.claimed is False
        assert target.first_time is False
        assert target.rerolled is False
        assert target.claimed_at is None

    def test_unique_constraint_account_week_slot(self) -> None:
        """Cannot create two targets for same account + week + slot."""
        RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
        )
        other_char = ObjectDBFactory(db_key="other_char")
        with pytest.raises(IntegrityError):
            RandomSceneTarget.objects.create(
                account=self.account,
                target_character=other_char,
                week_start=self.week_start,
                slot_number=1,
            )

    def test_different_slots_allowed(self) -> None:
        """Same account + week can have different slot numbers."""
        RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
        )
        other_char = ObjectDBFactory(db_key="slot2_char")
        target2 = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=other_char,
            week_start=self.week_start,
            slot_number=2,
        )
        assert target2.pk is not None

    def test_str(self) -> None:
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=3,
        )
        result = str(target)
        assert "rs_player" in result
        assert "target_char" in result
        assert "3" in result


class RandomSceneCompletionModelTest(TestCase):
    """Test RandomSceneCompletion model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rs_completer")
        cls.target_char = ObjectDBFactory(db_key="completed_char")

    def setUp(self) -> None:
        RandomSceneCompletion.flush_instance_cache()

    def test_create_completion(self) -> None:
        """Completion can be created and auto-sets completed_at."""
        completion = RandomSceneCompletion.objects.create(
            account=self.account,
            target_character=self.target_char,
        )
        assert completion.pk is not None
        assert completion.account == self.account
        assert completion.target_character == self.target_char
        assert completion.completed_at is not None

    def test_unique_constraint_account_target(self) -> None:
        """Cannot create two completions for same account + target_character."""
        RandomSceneCompletion.objects.create(
            account=self.account,
            target_character=self.target_char,
        )
        with pytest.raises(IntegrityError):
            RandomSceneCompletion.objects.create(
                account=self.account,
                target_character=self.target_char,
            )

    def test_different_targets_allowed(self) -> None:
        """Same account can complete with different target characters."""
        RandomSceneCompletion.objects.create(
            account=self.account,
            target_character=self.target_char,
        )
        other_char = ObjectDBFactory(db_key="other_completed")
        completion2 = RandomSceneCompletion.objects.create(
            account=self.account,
            target_character=other_char,
        )
        assert completion2.pk is not None

    def test_str(self) -> None:
        completion = RandomSceneCompletion.objects.create(
            account=self.account,
            target_character=self.target_char,
        )
        result = str(completion)
        assert "rs_completer" in result
        assert "completed_char" in result
