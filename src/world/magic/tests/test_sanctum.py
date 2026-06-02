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
    SanctumOwnerMode,
    Thread,
)
from world.magic.services.resonance import grant_resonance
from world.magic.services.sanctum import (
    SanctumInstallViaProjectError,
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
    kwargs: dict[str, object] = {
        "feature_instance": feature_instance,
        "resonance_type": overrides.pop("resonance_type", ResonanceFactory()),
        "owner_mode": overrides.pop("owner_mode", SanctumOwnerMode.PERSONAL),
    }
    if "founder_character_sheet" in overrides:
        kwargs["founder_character_sheet"] = overrides.pop("founder_character_sheet")
    kwargs.update(overrides)
    return SanctumDetails.objects.create(**kwargs)


class SanctumDetailsTests(TestCase):
    def test_str_contains_mode_and_resonance(self) -> None:
        sanctum = _sanctum_details()
        result = str(sanctum)
        self.assertIn("Sanctum#", result)
        self.assertIn("Personal", result)

    def test_founder_character_sheet_set_at_creation(self) -> None:
        founder = CharacterSheetFactory()
        sanctum = _sanctum_details(founder_character_sheet=founder)
        self.assertEqual(sanctum.founder_character_sheet, founder)

    def test_one_personal_per_founder_constraint(self) -> None:
        founder = CharacterSheetFactory()
        _sanctum_details(founder_character_sheet=founder, owner_mode=SanctumOwnerMode.PERSONAL)
        with self.assertRaises(IntegrityError):
            _sanctum_details(founder_character_sheet=founder, owner_mode=SanctumOwnerMode.PERSONAL)

    def test_covenant_sanctums_not_constrained_per_founder(self) -> None:
        """Same founder can lead multiple COVENANT Sanctification rites."""
        founder = CharacterSheetFactory()
        s1 = _sanctum_details(founder_character_sheet=founder, owner_mode=SanctumOwnerMode.COVENANT)
        s2 = _sanctum_details(founder_character_sheet=founder, owner_mode=SanctumOwnerMode.COVENANT)
        self.assertNotEqual(s1.pk, s2.pk)

    def test_null_founder_does_not_collide(self) -> None:
        """Pre-Sanctification rows or historical/seed data with null founder are allowed."""
        _sanctum_details(founder_character_sheet=None, owner_mode=SanctumOwnerMode.PERSONAL)
        _sanctum_details(founder_character_sheet=None, owner_mode=SanctumOwnerMode.PERSONAL)


class SanctumPendingPayoutTests(TestCase):
    def test_pending_payout_persists(self) -> None:
        from world.magic.models import SanctumPendingPayout

        sanctum = _sanctum_details()
        weaver = CharacterSheetFactory()
        row = SanctumPendingPayout.objects.create(
            sanctum=sanctum,
            weaver_character_sheet=weaver,
            pending_weaving=20,
            pending_owner_bonus=5,
        )
        self.assertEqual(row.total_pending(), 25)

    def test_unique_per_sanctum_weaver(self) -> None:
        from world.magic.models import SanctumPendingPayout

        sanctum = _sanctum_details()
        weaver = CharacterSheetFactory()
        SanctumPendingPayout.objects.create(
            sanctum=sanctum, weaver_character_sheet=weaver, pending_weaving=10
        )
        with self.assertRaises(IntegrityError):
            SanctumPendingPayout.objects.create(
                sanctum=sanctum, weaver_character_sheet=weaver, pending_weaving=99
            )


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


def _sanctum_progression_for_upgrade(
    *,
    target_level: int = 2,
    target_room_profile=None,
    target_feature_kind=None,
):
    """Build a RoomFeatureProgressionDetails for a Sanctum upgrade Project.

    Sanctum installs no longer flow through Project resolution
    (Plan 4 §F revised 2026-06-03 — install is ritual-driven). Tests
    that previously created SanctumInstallParams + ran target_level=1
    through handle_progression are removed.
    """
    sanctum_kind = target_feature_kind or RoomFeatureKindFactory(
        service_strategy=RoomFeatureServiceStrategy.SANCTUM,
    )
    project = ProjectFactory(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
    return RoomFeatureProgressionDetailsFactory(
        project=project,
        target_feature_kind=sanctum_kind,
        target_level=target_level,
        **({"target_room_profile": target_room_profile} if target_room_profile else {}),
    )


class HandleProgressionRejectsInstallTests(TestCase):
    def test_target_level_1_is_rejected(self) -> None:
        progression = _sanctum_progression_for_upgrade(target_level=1)
        with self.assertRaises(SanctumInstallViaProjectError):
            handle_progression(progression.project, target_level=1)


class HandleProgressionUpgradeTests(TestCase):
    def test_upgrade_bumps_level_and_timestamp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        sanctum_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.SANCTUM,
        )
        room_profile = RoomProfileFactory()
        # Pre-existing Sanctum (would normally come from Sanctification ritual)
        RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=sanctum_kind,
            level=1,
        )
        upgrade = _sanctum_progression_for_upgrade(
            target_level=2,
            target_room_profile=room_profile,
            target_feature_kind=sanctum_kind,
        )

        handle_progression(upgrade.project, target_level=2)

        instance = RoomFeatureInstance.objects.get(room_profile=room_profile)
        self.assertEqual(instance.level, 2)
        self.assertIsNotNone(instance.last_upgraded_at)

    def test_upgrade_without_existing_instance_raises(self) -> None:
        progression = _sanctum_progression_for_upgrade(target_level=2)
        with self.assertRaises(SanctumUpgradeMissingInstanceError):
            handle_progression(progression.project, target_level=2)

    def test_upgrade_against_wrong_kind_raises(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        sanctum_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.SANCTUM,
        )
        room_profile = RoomProfileFactory()
        # Pre-occupy room with a NON-sanctum feature.
        RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=RoomFeatureKindFactory(
                service_strategy=RoomFeatureServiceStrategy.LIBRARY,
                name="Library",
            ),
        )
        upgrade = _sanctum_progression_for_upgrade(
            target_level=2,
            target_room_profile=room_profile,
            target_feature_kind=sanctum_kind,
        )
        with self.assertRaises(SanctumUpgradeKindMismatchError):
            handle_progression(upgrade.project, target_level=2)


class StrategyRegistrationTests(TestCase):
    def test_strategy_registered_at_ready(self) -> None:
        from world.room_features.services import ROOM_FEATURE_STRATEGIES

        self.assertIn(RoomFeatureServiceStrategy.SANCTUM, ROOM_FEATURE_STRATEGIES)
        self.assertIs(
            ROOM_FEATURE_STRATEGIES[RoomFeatureServiceStrategy.SANCTUM],
            handle_progression,
        )
