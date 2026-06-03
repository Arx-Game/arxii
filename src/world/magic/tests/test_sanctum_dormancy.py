"""Tests for Sanctum dormancy gating (#671 Phase 5).

Covers ``world.magic.services.sanctum_cron._sanctum_is_dormant`` and the
public ``world.magic.services.sanctum_state.sanctum_is_dormant`` helper.
PERSONAL Sanctums gate on the founder; COVENANT Sanctums gate on the
union of current Sanctum-threaded weavers.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import ActivityState, LifecycleState
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import SanctumDetails, SanctumOwnerMode, Thread
from world.magic.services.sanctum_cron import _sanctum_is_dormant
from world.magic.services.sanctum_state import sanctum_is_dormant
from world.room_features.factories import (
    RoomFeatureInstanceFactory,
    RoomFeatureKindFactory,
)


def _build_sanctum(*, owner_mode=SanctumOwnerMode.PERSONAL, founder=None) -> SanctumDetails:
    feature_instance = RoomFeatureInstanceFactory(feature_kind=RoomFeatureKindFactory())
    return SanctumDetails.objects.create(
        feature_instance=feature_instance,
        resonance_type=ResonanceFactory(),
        owner_mode=owner_mode,
        founder_character_sheet=founder,
    )


def _attach_thread(sanctum: SanctumDetails, owner_sheet, *, retired: bool = False) -> Thread:
    # Build the SANCTUM thread directly — the generic ThreadFactory defaults
    # target_kind=TRAIT with a target_trait SubFactory, which violates the
    # thread_sanctum_payload constraint when overridden mid-build.
    slot = (
        SanctumSlotKind.COVENANT
        if sanctum.owner_mode == SanctumOwnerMode.COVENANT
        else SanctumSlotKind.HELPER
    )
    return Thread.objects.create(
        owner=owner_sheet,
        resonance=sanctum.resonance_type,
        target_kind=TargetKind.SANCTUM,
        target_sanctum_details=sanctum,
        slot_kind=slot,
        retired_at=timezone.now() if retired else None,
    )


class SanctumIsDormantPersonalTests(TestCase):
    def test_active_alive_founder_is_not_dormant(self):
        founder = CharacterSheetFactory()
        sanctum = _build_sanctum(founder=founder)
        self.assertFalse(_sanctum_is_dormant(sanctum, []))
        self.assertFalse(sanctum_is_dormant(sanctum))

    def test_inactive_founder_is_dormant(self):
        founder = CharacterSheetFactory(activity_state=ActivityState.INACTIVE)
        sanctum = _build_sanctum(founder=founder)
        self.assertTrue(_sanctum_is_dormant(sanctum, []))
        self.assertTrue(sanctum_is_dormant(sanctum))

    def test_dead_founder_is_dormant(self):
        founder = CharacterSheetFactory(lifecycle_state=LifecycleState.DEAD)
        sanctum = _build_sanctum(founder=founder)
        self.assertTrue(_sanctum_is_dormant(sanctum, []))

    def test_null_founder_is_dormant(self):
        sanctum = _build_sanctum(founder=None)
        self.assertTrue(_sanctum_is_dormant(sanctum, []))
        self.assertTrue(sanctum_is_dormant(sanctum))


class SanctumIsDormantCovenantTests(TestCase):
    def test_all_threaders_active_not_dormant(self):
        weaver_a = CharacterSheetFactory()
        weaver_b = CharacterSheetFactory()
        sanctum = _build_sanctum(owner_mode=SanctumOwnerMode.COVENANT)
        ta = _attach_thread(sanctum, weaver_a)
        tb = _attach_thread(sanctum, weaver_b)
        self.assertFalse(_sanctum_is_dormant(sanctum, [ta, tb]))

    def test_all_threaders_dormant_is_dormant(self):
        weaver_a = CharacterSheetFactory(activity_state=ActivityState.INACTIVE)
        weaver_b = CharacterSheetFactory(lifecycle_state=LifecycleState.RETIRED)
        sanctum = _build_sanctum(owner_mode=SanctumOwnerMode.COVENANT)
        ta = _attach_thread(sanctum, weaver_a)
        tb = _attach_thread(sanctum, weaver_b)
        self.assertTrue(_sanctum_is_dormant(sanctum, [ta, tb]))

    def test_single_active_threader_keeps_alive(self):
        weaver_a = CharacterSheetFactory(activity_state=ActivityState.INACTIVE)
        weaver_b = CharacterSheetFactory()  # ACTIVE/ALIVE
        sanctum = _build_sanctum(owner_mode=SanctumOwnerMode.COVENANT)
        ta = _attach_thread(sanctum, weaver_a)
        tb = _attach_thread(sanctum, weaver_b)
        self.assertFalse(_sanctum_is_dormant(sanctum, [ta, tb]))

    def test_public_helper_treats_no_threaders_as_dormant(self):
        sanctum = _build_sanctum(owner_mode=SanctumOwnerMode.COVENANT)
        # No threads at all — public helper says dormant (no income source).
        self.assertTrue(sanctum_is_dormant(sanctum))
