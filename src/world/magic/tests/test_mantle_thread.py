"""Tests for the MANTLE Thread kind (#512 Mantle system, Task 2).

A character anchors a Thread to a Mantle via target_kind=MANTLE +
target_mantle FK. Mirrors the FACET / COVENANT_ROLE discriminator pattern:
exactly-one-target CheckConstraint + per-(owner, target_mantle) active
UniqueConstraint.
"""

from django.db.utils import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import MantleFactory
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread


class MantleThreadTests(TestCase):
    def test_mantle_thread_creates_and_reads_back(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        mantle = MantleFactory()
        thread = Thread.objects.create(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
        )
        thread.full_clean()
        reloaded = Thread.objects.get(pk=thread.pk)
        self.assertEqual(reloaded.target_kind, TargetKind.MANTLE)
        self.assertEqual(reloaded.target_mantle, mantle)
        self.assertEqual(reloaded.target, mantle)

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
