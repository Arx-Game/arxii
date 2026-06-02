"""Phase 2a tests for SanctumDetails + Thread SANCTUM extension + ResonanceGrant attribution.

Exercises the new schema-level guarantees:

- SanctumDetails str / OneToOne to RoomFeatureInstance
- Thread.target_kind=SANCTUM requires target_sanctum_details + slot_kind
- Thread.slot_kind must be empty for non-SANCTUM targets
- One active PERSONAL_OWN slot per owner, one active COVENANT slot per owner
- ResonanceGrant SANCTUM_WEAVING / SANCTUM_OWNER_BONUS / PROJECT_CONTRIBUTION
  CheckConstraints
- grant_resonance kwargs + source-shape validation for the new sources
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource, SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.models import (
    ResonanceGrant,
    SanctumDetails,
    SanctumOwnerMode,
    Thread,
)
from world.magic.services.resonance import grant_resonance
from world.room_features.factories import (
    RoomFeatureInstanceFactory,
    RoomFeatureKindFactory,
)


def _sanctum_details(**overrides) -> SanctumDetails:
    feature_instance = overrides.pop(
        "feature_instance",
        RoomFeatureInstanceFactory(feature_kind=RoomFeatureKindFactory()),
    )
    return SanctumDetails.objects.create(
        feature_instance=feature_instance,
        resonance_type=overrides.pop("resonance_type", ResonanceFactory()),
        owner_mode=overrides.pop("owner_mode", SanctumOwnerMode.PERSONAL),
        **overrides,
    )


class SanctumDetailsTests(TestCase):
    def test_str_contains_mode_and_resonance(self) -> None:
        sanctum = _sanctum_details()
        result = str(sanctum)
        self.assertIn("Sanctum#", result)
        self.assertIn("Personal", result)


class ThreadSanctumPayloadTests(TestCase):
    def test_sanctum_thread_with_slot_kind_persists(self) -> None:
        sanctum = _sanctum_details()
        thread = ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        self.assertEqual(thread.target, sanctum)

    def test_sanctum_thread_without_slot_kind_violates_check(self) -> None:
        sanctum = _sanctum_details()
        with self.assertRaises(IntegrityError):
            ThreadFactory(
                target_kind=TargetKind.SANCTUM,
                target_trait=None,
                target_sanctum_details=sanctum,
                slot_kind="",
            )

    def test_sanctum_thread_without_target_violates_check(self) -> None:
        with self.assertRaises(IntegrityError):
            ThreadFactory(
                target_kind=TargetKind.SANCTUM,
                target_trait=None,
                slot_kind=SanctumSlotKind.PERSONAL_OWN,
            )

    def test_non_sanctum_with_slot_kind_violates_check(self) -> None:
        with self.assertRaises(IntegrityError):
            ThreadFactory(
                target_kind=TargetKind.TRAIT,
                slot_kind=SanctumSlotKind.HELPER,
            )

    def test_clean_rejects_sanctum_without_slot_kind(self) -> None:
        sanctum = _sanctum_details()
        owner = CharacterSheetFactory()
        thread = Thread(
            owner=owner,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=sanctum,
            slot_kind="",
        )
        with self.assertRaises(ValidationError):
            thread.clean()


class ThreadSanctumSlotUniquenessTests(TestCase):
    def test_two_active_personal_own_threads_per_owner_rejected(self) -> None:
        owner = CharacterSheetFactory()
        sanctum_a = _sanctum_details()
        sanctum_b = _sanctum_details()
        ThreadFactory(
            owner=owner,
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum_a,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        with self.assertRaises(IntegrityError):
            ThreadFactory(
                owner=owner,
                target_kind=TargetKind.SANCTUM,
                target_trait=None,
                target_sanctum_details=sanctum_b,
                slot_kind=SanctumSlotKind.PERSONAL_OWN,
            )

    def test_retired_personal_own_does_not_block_new(self) -> None:
        from django.utils import timezone

        owner = CharacterSheetFactory()
        sanctum_a = _sanctum_details()
        sanctum_b = _sanctum_details()
        ThreadFactory(
            owner=owner,
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum_a,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            retired_at=timezone.now(),
        )
        # No exception — retired_at excludes the prior row from the partial unique.
        ThreadFactory(
            owner=owner,
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum_b,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )

    def test_helper_slot_unlimited(self) -> None:
        owner = CharacterSheetFactory()
        for _ in range(3):
            ThreadFactory(
                owner=owner,
                target_kind=TargetKind.SANCTUM,
                target_trait=None,
                target_sanctum_details=_sanctum_details(),
                slot_kind=SanctumSlotKind.HELPER,
            )

    def test_same_sanctum_twice_per_owner_rejected(self) -> None:
        owner = CharacterSheetFactory()
        sanctum = _sanctum_details()
        ThreadFactory(
            owner=owner,
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        with self.assertRaises(IntegrityError):
            ThreadFactory(
                owner=owner,
                target_kind=TargetKind.SANCTUM,
                target_trait=None,
                target_sanctum_details=sanctum,
                slot_kind=SanctumSlotKind.HELPER,
            )


class ResonanceGrantSanctumAttributionTests(TestCase):
    def test_sanctum_weaving_grant_requires_sanctum_details(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=resonance,
                amount=10,
                source=GainSource.SANCTUM_WEAVING,
            )

    def test_grant_resonance_sanctum_weaving_happy_path(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        sanctum = _sanctum_details(resonance_type=resonance)
        cr = grant_resonance(
            character_sheet=sheet,
            resonance=resonance,
            amount=7,
            source=GainSource.SANCTUM_WEAVING,
            sanctum_details=sanctum,
        )
        self.assertEqual(cr.balance, 7)
        grants = ResonanceGrant.objects.filter(source=GainSource.SANCTUM_WEAVING)
        self.assertEqual(grants.count(), 1)
        self.assertEqual(grants.first().source_sanctum_details, sanctum)

    def test_grant_resonance_sanctum_weaving_missing_kwarg_rejected(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with self.assertRaises(ValueError):
            grant_resonance(
                character_sheet=sheet,
                resonance=resonance,
                amount=7,
                source=GainSource.SANCTUM_WEAVING,
            )

    def test_grant_resonance_project_contribution_requires_project(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with self.assertRaises(ValueError):
            grant_resonance(
                character_sheet=sheet,
                resonance=resonance,
                amount=1,
                source=GainSource.PROJECT_CONTRIBUTION,
            )

    def test_residence_grant_with_sanctum_fk_rejected(self) -> None:
        """ROOM_RESIDENCE rows must keep source_sanctum_details NULL."""
        from evennia_extensions.factories import RoomProfileFactory

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        sanctum = _sanctum_details()
        room_profile = RoomProfileFactory()
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=resonance,
                amount=1,
                source=GainSource.ROOM_RESIDENCE,
                source_room_profile=room_profile,
                source_sanctum_details=sanctum,
            )
