"""
Tests for Random Scene models.
"""

import datetime

from django.db import IntegrityError
from django.test import TestCase
import pytest

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.progression.models import RandomSceneCompletion, RandomSceneTarget
from world.roster.factories import RosterEntryFactory


class RandomSceneTargetModelTest(TestCase):
    """Test RandomSceneTarget model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rs_player")
        identity = CharacterIdentityFactory()
        cls.target_persona = identity.active_persona
        cls.week_start = datetime.date(2026, 3, 23)  # A Monday

    def setUp(self) -> None:
        RandomSceneTarget.flush_instance_cache()

    def test_create_with_all_fields(self) -> None:
        """Target can be created with all fields."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=self.target_persona,
            week_start=self.week_start,
            slot_number=1,
            claimed=True,
            first_time=True,
            rerolled=True,
        )
        assert target.pk is not None
        assert target.account == self.account
        assert target.target_persona == self.target_persona
        assert target.week_start == self.week_start
        assert target.slot_number == 1
        assert target.claimed is True
        assert target.first_time is True
        assert target.rerolled is True

    def test_default_values(self) -> None:
        """Defaults are claimed=False, first_time=False, rerolled=False."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=self.target_persona,
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
            target_persona=self.target_persona,
            week_start=self.week_start,
            slot_number=1,
        )
        other_identity = CharacterIdentityFactory()
        with pytest.raises(IntegrityError):
            RandomSceneTarget.objects.create(
                account=self.account,
                target_persona=other_identity.active_persona,
                week_start=self.week_start,
                slot_number=1,
            )

    def test_different_slots_allowed(self) -> None:
        """Same account + week can have different slot numbers."""
        RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=self.target_persona,
            week_start=self.week_start,
            slot_number=1,
        )
        other_identity = CharacterIdentityFactory()
        target2 = RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=other_identity.active_persona,
            week_start=self.week_start,
            slot_number=2,
        )
        assert target2.pk is not None

    def test_str(self) -> None:
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=self.target_persona,
            week_start=self.week_start,
            slot_number=3,
        )
        result = str(target)
        assert "rs_player" in result
        assert "3" in result


class RandomSceneCompletionModelTest(TestCase):
    """Test RandomSceneCompletion model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rs_completer")
        cls.claimer_entry = RosterEntryFactory()
        identity = CharacterIdentityFactory()
        cls.target_persona = identity.active_persona

    def setUp(self) -> None:
        RandomSceneCompletion.flush_instance_cache()

    def test_create_completion(self) -> None:
        """Completion can be created and auto-sets completed_at."""
        completion = RandomSceneCompletion.objects.create(
            account=self.account,
            claimer_entry=self.claimer_entry,
            target_persona=self.target_persona,
        )
        assert completion.pk is not None
        assert completion.account == self.account
        assert completion.claimer_entry == self.claimer_entry
        assert completion.target_persona == self.target_persona
        assert completion.completed_at is not None

    def test_unique_constraint_account_target(self) -> None:
        """Cannot create two completions for same account + target_persona."""
        RandomSceneCompletion.objects.create(
            account=self.account,
            claimer_entry=self.claimer_entry,
            target_persona=self.target_persona,
        )
        with pytest.raises(IntegrityError):
            RandomSceneCompletion.objects.create(
                account=self.account,
                claimer_entry=self.claimer_entry,
                target_persona=self.target_persona,
            )

    def test_different_targets_allowed(self) -> None:
        """Same account can complete with different target personas."""
        RandomSceneCompletion.objects.create(
            account=self.account,
            claimer_entry=self.claimer_entry,
            target_persona=self.target_persona,
        )
        other_identity = CharacterIdentityFactory()
        completion2 = RandomSceneCompletion.objects.create(
            account=self.account,
            claimer_entry=self.claimer_entry,
            target_persona=other_identity.active_persona,
        )
        assert completion2.pk is not None

    def test_str(self) -> None:
        completion = RandomSceneCompletion.objects.create(
            account=self.account,
            claimer_entry=self.claimer_entry,
            target_persona=self.target_persona,
        )
        result = str(completion)
        assert "completion" in result.lower() or "RS" in result
