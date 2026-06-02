"""Phase 3 tests: LVM helpers + Homecoming + Purging + weaving + cron tick + seeds."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, KeyType, LocationParentType
from world.locations.factories import LocationOwnershipFactory
from world.locations.models import LocationValueModifier
from world.locations.services import effective_value
from world.magic.constants import GainSource, SanctumSlotKind, TargetKind
from world.magic.exceptions import ResonanceInsufficient
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
)
from world.magic.models import (
    CharacterResonance,
    ResonanceGrant,
    SanctumDetails,
    SanctumOwnerMode,
)
from world.magic.seeds_sanctum import (
    HOMECOMING_RITUAL_NAME,
    PURGING_RITUAL_NAME,
    ensure_homecoming_ritual,
    ensure_purging_ritual,
    ensure_sanctum_rituals,
)
from world.magic.services.sanctum_cron import (
    K_INCOME_RATE,
    LEVEL_MULTIPLIERS,
    sanctum_resonance_generation_tick,
)
from world.magic.services.sanctum_lvm import (
    apply_homecoming_gain,
    drain_homecoming_for_purge,
    homecoming_source_tag,
    retag_homecoming_for_new_resonance,
    sum_homecoming_value,
)
from world.magic.services.sanctum_rituals import (
    HomecomingLeaderNotOwnerError,
    HomecomingResult,
    PurgingResonanceTypeUnchangedError,
    perform_homecoming_ritual,
    perform_purging_ritual,
)
from world.magic.services.sanctum_weaving import (
    SanctumWeavingHelperByOwnerError,
    SanctumWeavingLevelCapError,
    SanctumWeavingNotOwnerError,
    sever_sanctum_thread,
    weave_sanctum_thread,
)
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import (
    RoomFeatureInstanceFactory,
    RoomFeatureKindFactory,
)
from world.scenes.factories import PersonaFactory


def _personal_sanctum(*, resonance=None, level: int = 1) -> tuple[SanctumDetails, object]:
    """Build a PERSONAL Sanctum + its room/owner. Returns (sanctum, owner_persona)."""
    resonance = resonance or ResonanceFactory()
    room_profile = RoomProfileFactory()
    owner_persona = PersonaFactory()
    LocationOwnershipFactory(
        parent_type=LocationParentType.ROOM,
        area=None,
        room_profile=room_profile,
        holder_type=HolderType.PERSONA,
        holder_persona=owner_persona,
        holder_organization=None,
    )
    sanctum_kind = RoomFeatureKindFactory(
        service_strategy=RoomFeatureServiceStrategy.SANCTUM,
    )
    instance = RoomFeatureInstanceFactory(
        room_profile=room_profile,
        feature_kind=sanctum_kind,
        level=level,
    )
    sanctum = SanctumDetails.objects.create(
        feature_instance=instance,
        resonance_type=resonance,
        owner_mode=SanctumOwnerMode.PERSONAL,
    )
    return sanctum, owner_persona


class LVMHelpersTests(TestCase):
    def test_apply_creates_row_and_returns_applied(self) -> None:
        sanctum, _ = _personal_sanctum()
        applied, overflow = apply_homecoming_gain(sanctum, gain=20, cap=100)
        self.assertEqual(applied, 20)
        self.assertEqual(overflow, 0)
        self.assertEqual(sum_homecoming_value(sanctum), 20)
        row = LocationValueModifier.objects.get(source=homecoming_source_tag(sanctum))
        self.assertEqual(row.key_type, KeyType.RESONANCE)
        self.assertEqual(row.parent_type, LocationParentType.ROOM)
        self.assertEqual(row.value, 20)

    def test_apply_increments_existing_row(self) -> None:
        sanctum, _ = _personal_sanctum()
        apply_homecoming_gain(sanctum, gain=20, cap=100)
        applied, overflow = apply_homecoming_gain(sanctum, gain=15, cap=100)
        self.assertEqual(applied, 15)
        self.assertEqual(overflow, 0)
        self.assertEqual(sum_homecoming_value(sanctum), 35)

    def test_apply_caps_and_returns_overflow(self) -> None:
        sanctum, _ = _personal_sanctum()
        apply_homecoming_gain(sanctum, gain=80, cap=100)
        applied, overflow = apply_homecoming_gain(sanctum, gain=50, cap=100)
        self.assertEqual(applied, 20)
        self.assertEqual(overflow, 30)
        self.assertEqual(sum_homecoming_value(sanctum), 100)

    def test_drain_multiplies_value_by_retention(self) -> None:
        sanctum, _ = _personal_sanctum()
        apply_homecoming_gain(sanctum, gain=100, cap=100)
        drain_homecoming_for_purge(sanctum, Decimal("0.5"))
        self.assertEqual(sum_homecoming_value(sanctum), 50)

    def test_retag_swaps_resonance(self) -> None:
        sanctum, _ = _personal_sanctum()
        apply_homecoming_gain(sanctum, gain=10, cap=100)
        new_resonance = ResonanceFactory()
        retag_homecoming_for_new_resonance(sanctum, new_resonance)
        row = LocationValueModifier.objects.get(source=homecoming_source_tag(sanctum))
        self.assertEqual(row.resonance_id, new_resonance.pk)


class HomecomingRitualTests(TestCase):
    def test_owner_can_perform_and_grow_resonance(self) -> None:
        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance)
        # Seed leader's pool. Path level defaults to >0 in factory chain.
        CharacterResonanceFactory(
            character_sheet=owner.character_sheet,
            resonance=resonance,
            balance=1000,
        )
        result = perform_homecoming_ritual(
            sanctum,
            owner,
            resonance_sacrificed=500,
            narrative_text="A first consecration.",
        )
        self.assertIsInstance(result, HomecomingResult)
        # 500 sacrificed at the 100:1 efficiency ratio yields 5 imbued.
        self.assertEqual(result.base_resonance_added, 5)
        self.assertEqual(result.overflow_escrowed, 0)
        self.assertEqual(result.new_homecoming_sum, 5)
        cr = CharacterResonance.objects.get(
            character_sheet=owner.character_sheet, resonance=resonance
        )
        self.assertEqual(cr.balance, 500)  # 1000 - 500 sacrificed
        sanctum.refresh_from_db()
        self.assertIsNotNone(sanctum.last_homecoming_ritual_at)

    def test_non_owner_cannot_perform(self) -> None:
        resonance = ResonanceFactory()
        sanctum, _ = _personal_sanctum(resonance=resonance)
        intruder = PersonaFactory()
        CharacterResonanceFactory(
            character_sheet=intruder.character_sheet,
            resonance=resonance,
            balance=1000,
        )
        with self.assertRaises(HomecomingLeaderNotOwnerError):
            perform_homecoming_ritual(sanctum, intruder, resonance_sacrificed=100)

    def test_insufficient_balance_rejected(self) -> None:
        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance)
        CharacterResonanceFactory(
            character_sheet=owner.character_sheet, resonance=resonance, balance=10
        )
        with self.assertRaises(ResonanceInsufficient):
            perform_homecoming_ritual(sanctum, owner, resonance_sacrificed=100)


class PurgingRitualTests(TestCase):
    def test_purging_changes_resonance_and_drains_rows(self) -> None:
        old_resonance = ResonanceFactory()
        new_resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=old_resonance)
        # Seed Homecoming-source row with 100 then leader pool to pay purging cost.
        apply_homecoming_gain(sanctum, gain=100, cap=200)
        CharacterResonanceFactory(
            character_sheet=owner.character_sheet,
            resonance=old_resonance,
            balance=500,
        )

        result = perform_purging_ritual(
            sanctum,
            owner,
            new_resonance=new_resonance,
            resonance_sacrificed=100,
        )

        self.assertEqual(result.new_resonance_id, new_resonance.pk)
        # 100 × DEFAULT_PURGING_RETENTION (0.5) = 50
        self.assertEqual(result.sum_after_drain, 50)
        sanctum.refresh_from_db()
        self.assertEqual(sanctum.resonance_type_id, new_resonance.pk)
        row = LocationValueModifier.objects.get(source=homecoming_source_tag(sanctum))
        self.assertEqual(row.resonance_id, new_resonance.pk)
        self.assertEqual(row.value, 50)

    def test_same_resonance_rejected(self) -> None:
        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance)
        CharacterResonanceFactory(
            character_sheet=owner.character_sheet, resonance=resonance, balance=500
        )
        with self.assertRaises(PurgingResonanceTypeUnchangedError):
            perform_purging_ritual(
                sanctum, owner, new_resonance=resonance, resonance_sacrificed=100
            )


class WeavingTests(TestCase):
    def test_personal_own_by_owner_succeeds(self) -> None:
        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance)
        thread = weave_sanctum_thread(sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN)
        self.assertEqual(thread.target_kind, TargetKind.SANCTUM)
        self.assertEqual(thread.target_sanctum_details, sanctum)
        self.assertEqual(thread.slot_kind, SanctumSlotKind.PERSONAL_OWN)

    def test_personal_own_by_non_owner_rejected(self) -> None:
        sanctum, _ = _personal_sanctum()
        intruder = CharacterSheetFactory()
        with self.assertRaises(SanctumWeavingNotOwnerError):
            weave_sanctum_thread(sanctum, intruder, SanctumSlotKind.PERSONAL_OWN)

    def test_helper_by_owner_rejected(self) -> None:
        sanctum, owner = _personal_sanctum()
        with self.assertRaises(SanctumWeavingHelperByOwnerError):
            weave_sanctum_thread(sanctum, owner.character_sheet, SanctumSlotKind.HELPER)

    def test_helper_by_non_owner_succeeds(self) -> None:
        sanctum, _ = _personal_sanctum(level=3)
        helper = CharacterSheetFactory()
        thread = weave_sanctum_thread(sanctum, helper, SanctumSlotKind.HELPER)
        self.assertEqual(thread.slot_kind, SanctumSlotKind.HELPER)

    def test_level_cap_enforced_on_personal_sanctum(self) -> None:
        # level=1 means max 1 active SANCTUM thread on this sanctum.
        sanctum, owner = _personal_sanctum(level=1)
        weave_sanctum_thread(sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN)
        helper = CharacterSheetFactory()
        with self.assertRaises(SanctumWeavingLevelCapError):
            weave_sanctum_thread(sanctum, helper, SanctumSlotKind.HELPER)

    def test_sever_sets_retired_at_and_allows_reweave(self) -> None:
        sanctum, owner = _personal_sanctum()
        thread = weave_sanctum_thread(sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN)
        sever_sanctum_thread(thread)
        thread.refresh_from_db()
        self.assertIsNotNone(thread.retired_at)
        # Re-weave should now succeed (retired_at excludes prior row from unique).
        new_thread = weave_sanctum_thread(
            sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN
        )
        self.assertNotEqual(new_thread.pk, thread.pk)


class CronTickTests(TestCase):
    def test_cron_accumulates_into_pending_payout(self) -> None:
        from world.magic.models import SanctumPendingPayout

        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance, level=2)
        # Seed an ambient resonance row so effective_value() > 0
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=sanctum.feature_instance.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=1000,
            change_per_day=0,
            source="authored",
        )
        # Weave the owner in at PERSONAL_OWN with a non-zero thread level so income computes.
        thread = weave_sanctum_thread(sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN)
        thread.level = 5
        thread.save(update_fields=["level"])

        result = sanctum_resonance_generation_tick()

        self.assertGreaterEqual(result["sanctums_processed"], 1)
        self.assertGreaterEqual(result["weavers_accrued"], 1)
        # Cron should NOT have fired grant_resonance — accrue into pending pool.
        self.assertFalse(
            ResonanceGrant.objects.filter(
                character_sheet=owner.character_sheet,
                source=GainSource.SANCTUM_WEAVING,
            ).exists()
        )
        payout = SanctumPendingPayout.objects.get(
            sanctum=sanctum, weaver_character_sheet=owner.character_sheet
        )
        # Expected income: max(level, 1) × pool × multiplier × K
        # = 5 × 1000 × 1.5 (level 2 multiplier) × 0.01 = 75
        expected = int(
            Decimal(5)
            * Decimal(
                effective_value(sanctum.feature_instance.room_profile.objectdb, resonance=resonance)
            )
            * LEVEL_MULTIPLIERS[1]
            * K_INCOME_RATE
        )
        self.assertEqual(payout.pending_weaving, expected)
        self.assertEqual(payout.pending_owner_bonus, 0)

    def test_cron_skips_sanctum_with_no_threads(self) -> None:
        sanctum, _ = _personal_sanctum()
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=sanctum.feature_instance.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=sanctum.resonance_type,
            value=500,
            change_per_day=0,
            source="authored",
        )
        result = sanctum_resonance_generation_tick()
        self.assertEqual(result["weavers_accrued"], 0)

    def test_owner_bonus_accrued_when_multiple_threads(self) -> None:
        from world.magic.models import SanctumPendingPayout

        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance, level=3)
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=sanctum.feature_instance.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=100,
            change_per_day=0,
            source="authored",
        )
        owner_thread = weave_sanctum_thread(
            sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN
        )
        owner_thread.level = 1
        owner_thread.save(update_fields=["level"])
        helper_sheet = CharacterSheetFactory()
        helper_thread = weave_sanctum_thread(sanctum, helper_sheet, SanctumSlotKind.HELPER)
        helper_thread.level = 1
        helper_thread.save(update_fields=["level"])

        sanctum_resonance_generation_tick()

        # Owner pending row has bonus = 1 (one other thread).
        owner_payout = SanctumPendingPayout.objects.get(
            sanctum=sanctum, weaver_character_sheet=owner.character_sheet
        )
        self.assertEqual(owner_payout.pending_owner_bonus, 1)
        # Helper pending row has bonus = 0 (not owner).
        helper_payout = SanctumPendingPayout.objects.get(
            sanctum=sanctum, weaver_character_sheet=helper_sheet
        )
        self.assertEqual(helper_payout.pending_owner_bonus, 0)

    def test_cron_clamps_at_cap(self) -> None:
        from world.magic.models import SanctumPendingPayout
        from world.magic.models.sanctum import SANCTUM_PENDING_PAYOUT_CAP

        resonance = ResonanceFactory()
        sanctum, owner = _personal_sanctum(resonance=resonance, level=1)
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=sanctum.feature_instance.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=100000,  # huge pool — single tick would massively exceed cap
            change_per_day=0,
            source="authored",
        )
        thread = weave_sanctum_thread(sanctum, owner.character_sheet, SanctumSlotKind.PERSONAL_OWN)
        thread.level = 10
        thread.save(update_fields=["level"])

        sanctum_resonance_generation_tick()
        payout = SanctumPendingPayout.objects.get(
            sanctum=sanctum, weaver_character_sheet=owner.character_sheet
        )
        self.assertEqual(payout.total_pending(), SANCTUM_PENDING_PAYOUT_CAP)


class SeedsTests(TestCase):
    def test_seeds_idempotent(self) -> None:
        ensure_sanctum_rituals()
        ensure_sanctum_rituals()
        from world.magic.models import Ritual

        homecoming = Ritual.objects.get(name=HOMECOMING_RITUAL_NAME)
        purging = Ritual.objects.get(name=PURGING_RITUAL_NAME)
        self.assertEqual(homecoming.execution_kind, "SERVICE")
        self.assertIn("perform_homecoming_ritual", homecoming.service_function_path)
        self.assertIn("perform_purging_ritual", purging.service_function_path)

    def test_individual_helpers_idempotent(self) -> None:
        r1 = ensure_homecoming_ritual()
        r2 = ensure_homecoming_ritual()
        self.assertEqual(r1.pk, r2.pk)
        p1 = ensure_purging_ritual()
        p2 = ensure_purging_ritual()
        self.assertEqual(p1.pk, p2.pk)
