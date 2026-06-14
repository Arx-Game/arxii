"""Tests for the MANTLE Thread kind (#512 Mantle system, Task 2).

A character anchors a Thread to a Mantle via target_kind=MANTLE +
target_mantle FK. Mirrors the FACET / COVENANT_ROLE discriminator pattern:
exactly-one-target CheckConstraint + per-(owner, target_mantle) active
UniqueConstraint.
"""

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import MantleFactory
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.traits.factories import TraitFactory


class MantleThreadTests(TestCase):
    def test_mantle_thread_creates_and_reads_back(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        mantle = MantleFactory()
        # Validate the unsaved instance first (siblings exercise clean() pre-persist).
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
        )
        thread.full_clean()
        thread.save()
        reloaded = Thread.objects.get(pk=thread.pk)
        self.assertEqual(reloaded.target_kind, TargetKind.MANTLE)
        self.assertEqual(reloaded.target_mantle, mantle)
        self.assertEqual(reloaded.target, mantle)

    def test_retired_mantle_thread_allows_new_active_thread_on_same_mantle(self) -> None:
        """Retiring a mantle thread (setting retired_at) must allow a new active
        thread on the same (owner, mantle) — proves the partial-unique
        retired_at__isnull=True condition."""
        sheet = CharacterSheetFactory()
        mantle = MantleFactory()
        res_a = ResonanceFactory()
        res_b = ResonanceFactory()
        retired = Thread.objects.create(
            owner=sheet,
            resonance=res_a,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
        )
        retired.retired_at = timezone.now()
        retired.save()
        new_thread = Thread.objects.create(
            owner=sheet,
            resonance=res_b,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
        )
        self.assertIsNone(new_thread.retired_at)

    def test_check_constraint_rejects_mantle_with_extra_fk(self) -> None:
        """Setting both target_mantle and another target_* FK under MANTLE kind
        must fail at the DB layer."""
        sheet = CharacterSheetFactory()
        mantle = MantleFactory()
        trait = TraitFactory()
        with self.assertRaises(IntegrityError):
            Thread.objects.create(
                owner=sheet,
                resonance=ResonanceFactory(),
                target_kind=TargetKind.MANTLE,
                target_mantle=mantle,
                target_trait=trait,
            )

    def test_clean_rejects_mantle_kind_without_target_mantle(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.MANTLE,
        )
        with self.assertRaises(ValidationError):
            thread.full_clean()

    def test_second_active_mantle_thread_same_owner_target_collides(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        mantle = MantleFactory()
        Thread.objects.create(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
        )
        with self.assertRaises(IntegrityError):
            Thread.objects.create(
                owner=sheet,
                resonance=res,
                target_kind=TargetKind.MANTLE,
                target_mantle=mantle,
            )
