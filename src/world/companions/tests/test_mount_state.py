"""Tests for mount/dismount state (#1843)."""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.create import create_object

from typeclasses.companions import CompanionObject
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import RiskLevel
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.models import Companion
from world.companions.mount_content import (
    MOUNTED_CONDITION_NAME,
    ensure_mount_conditions,
)
from world.companions.services import (
    MountError,
    dismount_companion,
    mount_companion,
    resolve_companion_defeat,
)
from world.conditions.models import ConditionTemplate
from world.conditions.services import has_condition


def _present_companion(**kwargs) -> Companion:
    """A CompanionFactory instance with a live CompanionObject (mount-eligible)."""
    companion = CompanionFactory(**kwargs)
    obj = create_object(CompanionObject, key=companion.name, nohome=True)
    companion.objectdb = obj
    companion.save(update_fields=["objectdb"])
    return companion


class MountDismountTests(TestCase):
    def setUp(self) -> None:
        ensure_mount_conditions()
        self.sheet = CharacterSheetFactory()
        self.mount_archetype = CompanionArchetypeFactory(is_mount=True)
        self.companion = _present_companion(owner=self.sheet, archetype=self.mount_archetype)

    def _mounted_template(self) -> ConditionTemplate:
        return ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)

    def test_mount_applies_mounted_condition(self) -> None:
        mount_companion(self.sheet, self.companion)
        self.companion.refresh_from_db()
        self.assertEqual(self.companion.ridden_by_id, self.sheet.pk)
        self.assertTrue(has_condition(self.sheet.character, self._mounted_template()))

    def test_dismount_removes_mounted_condition(self) -> None:
        mount_companion(self.sheet, self.companion)
        dismount_companion(self.sheet)
        self.companion.refresh_from_db()
        self.assertIsNone(self.companion.ridden_by_id)
        self.assertFalse(has_condition(self.sheet.character, self._mounted_template()))

    def test_dismount_without_mount_raises(self) -> None:
        with self.assertRaises(MountError):
            dismount_companion(self.sheet)

    def test_mount_non_mount_archetype_rejected(self) -> None:
        non_mount = _present_companion(owner=self.sheet, archetype=CompanionArchetypeFactory())
        with self.assertRaises(MountError):
            mount_companion(self.sheet, non_mount)

    def test_mount_someone_elses_companion_rejected(self) -> None:
        other_sheet = CharacterSheetFactory()
        with self.assertRaises(MountError):
            mount_companion(other_sheet, self.companion)

    def test_cannot_mount_two_companions_at_once(self) -> None:
        second_companion = _present_companion(owner=self.sheet, archetype=self.mount_archetype)
        mount_companion(self.sheet, self.companion)
        with self.assertRaises(MountError):
            mount_companion(self.sheet, second_companion)

    def test_cannot_mount_already_ridden_companion(self) -> None:
        other_sheet = CharacterSheetFactory()
        mount_companion(self.sheet, self.companion)
        with self.assertRaises(MountError):
            mount_companion(other_sheet, self.companion)

    def test_companion_defeat_force_dismounts_rider(self) -> None:
        mount_companion(self.sheet, self.companion)
        # Run enough lethal draws that a "die" outcome lands (matches the
        # existing probabilistic pattern in test_defeat_consequences.py).
        released = False
        for _ in range(50):
            if resolve_companion_defeat(self.companion, RiskLevel.LETHAL):
                released = True
                break
        self.assertTrue(released, "Expected at least one lethal draw to release the companion.")
        self.companion.refresh_from_db()
        self.assertFalse(self.companion.is_active)
        self.assertIsNone(self.companion.ridden_by_id)
        self.assertFalse(has_condition(self.sheet.character, self._mounted_template()))
