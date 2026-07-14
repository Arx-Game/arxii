"""Thread.target_gift integrity: clean() + CheckConstraint + partial UniqueConstraint.

GIFT-kind threads anchor to a Gift via target_kind=GIFT + target_gift FK.
Mirrors the COVENANT_ROLE discriminator pattern: exactly-one-target
CheckConstraint + per-(owner, target_gift) partial UniqueConstraint WHERE
retired_at IS NULL — one active GIFT thread per gift (decision 7, #1578).
Multi-resonance is a deferred follow-up (#1619).

The clean()-only tests use unsaved Thread instances (the same idiom as
test_mantle_thread.py) so the DB CheckConstraint does not fire before
full_clean(); constraint tests use Thread.objects.create().
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import Thread
from world.traits.factories import TraitFactory


class ThreadTargetGiftIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()

    def _make(self, **overrides):
        """Build an unsaved valid GIFT-kind Thread (defaults) with overrides."""
        defaults = {
            "owner": self.sheet,
            "resonance": self.resonance,
            "target_kind": TargetKind.GIFT,
            "target_gift": self.gift,
        }
        defaults.update(overrides)
        return Thread(**defaults)

    def test_gift_thread_clean_valid(self) -> None:
        t = self._make()
        t.full_clean()  # no raise

    def test_gift_thread_clean_missing_target_gift(self) -> None:
        t = self._make(target_gift=None)
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_gift_thread_clean_other_target_set(self) -> None:
        # target_gift set but target_kind=TRAIT -> mismatch (target_gift stray).
        t = self._make(target_kind=TargetKind.TRAIT, target_trait=TraitFactory())
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_check_constraint_rejects_gift_with_extra_fk(self) -> None:
        """Setting both target_gift and target_trait under GIFT kind must fail
        at the DB layer."""
        with self.assertRaises(IntegrityError):
            Thread.objects.create(
                owner=self.sheet,
                resonance=self.resonance,
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
                target_trait=TraitFactory(),
            )

    def test_unique_active_gift_thread_per_owner_gift(self) -> None:
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Thread.objects.create(
                    owner=self.sheet,
                    resonance=self.resonance,
                    target_kind=TargetKind.GIFT,
                    target_gift=self.gift,
                )  # duplicate (owner, gift), both active

    def test_unique_active_gift_thread_allows_different_resonance(self) -> None:
        # The constraint is (owner, target_gift, resonance) per #1619:
        # a second active thread on the same gift at a DIFFERENT resonance
        # is now allowed (multi-resonance). But a duplicate at the SAME
        # resonance is still rejected.
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        other_resonance = ResonanceFactory()
        # Different resonance → allowed.
        Thread.objects.create(
            owner=self.sheet,
            resonance=other_resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        # Same resonance → rejected.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Thread.objects.create(
                    owner=self.sheet,
                    resonance=self.resonance,
                    target_kind=TargetKind.GIFT,
                    target_gift=self.gift,
                )

    def test_retired_gift_thread_not_unique_conflict(self) -> None:
        first = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        first.retired_at = timezone.now()
        first.save(update_fields=["retired_at"])
        # second active thread on same (owner, resonance, gift) now allowed
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )  # no raise
