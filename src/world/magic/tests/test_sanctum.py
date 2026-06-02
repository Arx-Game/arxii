"""Tests for SanctumDetails + Thread/SANCTUM + ResonanceGrant attribution + Sanctum strategy.

Exercises the Phase 2 schema-level guarantees and the
:func:`world.magic.services.sanctum.handle_progression` strategy
dispatched by the Room Features framework on project resolution.
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
    SanctumInstallParams,
    SanctumOwnerMode,
    Thread,
)
from world.magic.services.resonance import grant_resonance
from world.magic.services.sanctum import (
    SanctumAlreadyInstalledError,
    SanctumInstallParamsMissingError,
    SanctumUpgradeKindMismatchError,
    SanctumUpgradeMissingInstanceError,
    handle_progression,
)
from world.projects.constants import ProjectKind
from world.projects.factories import ProjectFactory
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import (
    RoomFeatureInstanceFactory,
    RoomFeatureKindFactory,
    RoomFeatureProgressionDetailsFactory,
)
from world.room_features.models import RoomFeatureInstance


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


def _sanctum_progression(*, target_level: int = 1, resonance=None, owner_mode=None):
    """Build a RoomFeatureProgressionDetails + SanctumInstallParams pair."""
    sanctum_kind = RoomFeatureKindFactory(
        service_strategy=RoomFeatureServiceStrategy.SANCTUM,
    )
    project = ProjectFactory(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
    progression = RoomFeatureProgressionDetailsFactory(
        project=project,
        target_feature_kind=sanctum_kind,
        target_level=target_level,
    )
    SanctumInstallParams.objects.create(
        progression_details=progression,
        resonance_type=resonance or ResonanceFactory(),
        declared_owner_mode=owner_mode or SanctumOwnerMode.PERSONAL,
    )
    return progression


class HandleProgressionInstallTests(TestCase):
    def test_install_creates_instance_and_details(self) -> None:
        resonance = ResonanceFactory()
        progression = _sanctum_progression(resonance=resonance)

        handle_progression(progression.project, target_level=1)

        instance = RoomFeatureInstance.objects.get(room_profile=progression.target_room_profile)
        self.assertEqual(instance.level, 1)
        self.assertEqual(instance.feature_kind, progression.target_feature_kind)
        details = SanctumDetails.objects.get(feature_instance=instance)
        self.assertEqual(details.resonance_type, resonance)
        self.assertEqual(details.owner_mode, SanctumOwnerMode.PERSONAL)

    def test_install_without_install_params_raises(self) -> None:
        sanctum_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.SANCTUM,
        )
        project = ProjectFactory(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        RoomFeatureProgressionDetailsFactory(
            project=project,
            target_feature_kind=sanctum_kind,
            target_level=1,
        )
        with self.assertRaises(SanctumInstallParamsMissingError):
            handle_progression(project, target_level=1)

    def test_install_into_already_occupied_room_rejected(self) -> None:
        progression = _sanctum_progression()
        # Pre-occupy with a Library feature.
        RoomFeatureInstanceFactory(
            room_profile=progression.target_room_profile,
            feature_kind=RoomFeatureKindFactory(
                service_strategy=RoomFeatureServiceStrategy.LIBRARY,
                name="Library",
            ),
        )
        with self.assertRaises(SanctumAlreadyInstalledError):
            handle_progression(progression.project, target_level=1)


class HandleProgressionUpgradeTests(TestCase):
    def test_upgrade_bumps_level_and_timestamp(self) -> None:
        install_progression = _sanctum_progression(target_level=1)
        handle_progression(install_progression.project, target_level=1)

        upgrade_project = ProjectFactory(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        upgrade_progression = RoomFeatureProgressionDetailsFactory(
            project=upgrade_project,
            target_room_profile=install_progression.target_room_profile,
            target_feature_kind=install_progression.target_feature_kind,
            target_level=2,
        )

        handle_progression(upgrade_progression.project, target_level=2)

        instance = RoomFeatureInstance.objects.get(
            room_profile=install_progression.target_room_profile
        )
        self.assertEqual(instance.level, 2)
        self.assertIsNotNone(instance.last_upgraded_at)

    def test_upgrade_without_existing_instance_raises(self) -> None:
        progression = _sanctum_progression(target_level=2)
        with self.assertRaises(SanctumUpgradeMissingInstanceError):
            handle_progression(progression.project, target_level=2)

    def test_upgrade_against_wrong_kind_raises(self) -> None:
        install_progression = _sanctum_progression()
        # Pre-occupy room with a NON-sanctum feature instead of running install.
        RoomFeatureInstanceFactory(
            room_profile=install_progression.target_room_profile,
            feature_kind=RoomFeatureKindFactory(
                service_strategy=RoomFeatureServiceStrategy.LIBRARY,
                name="Library",
            ),
        )
        upgrade_project = ProjectFactory(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        upgrade_progression = RoomFeatureProgressionDetailsFactory(
            project=upgrade_project,
            target_room_profile=install_progression.target_room_profile,
            target_feature_kind=install_progression.target_feature_kind,
            target_level=2,
        )
        with self.assertRaises(SanctumUpgradeKindMismatchError):
            handle_progression(upgrade_progression.project, target_level=2)


class StrategyRegistrationTests(TestCase):
    def test_strategy_registered_at_ready(self) -> None:
        from world.room_features.services import ROOM_FEATURE_STRATEGIES

        self.assertIn(RoomFeatureServiceStrategy.SANCTUM, ROOM_FEATURE_STRATEGIES)
        self.assertIs(
            ROOM_FEATURE_STRATEGIES[RoomFeatureServiceStrategy.SANCTUM],
            handle_progression,
        )
