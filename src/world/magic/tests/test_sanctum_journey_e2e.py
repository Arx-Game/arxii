"""Telnet E2E: sanctum lifecycle via CmdSanctum — all 7 subverbs (#1497).

Drives the full player journey through the sanctum lifecycle using
CmdSanctum command objects (the telnet surface) on high-fidelity fixtures:

  install → weave helper → homecoming → purging → absorb → sever → dissolve

Each step asserts DB state, confirming the action.run() seam fired
the correct service and the side-effects landed in the expected models.

Two characters are needed because the owner cannot use ``slot=helper``
(``SanctumWeavingHelperByOwnerError``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.sanctum import CmdSanctum
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.factories import LocationOwnershipFactory
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import (
    CharacterResonance,
    SanctumDetails,
    SanctumOwnerMode,
    SanctumPendingPayout,
    Thread,
)
from world.magic.seeds_checks import ensure_magic_check_content
from world.magic.seeds_sanctum import ensure_sanctum_rituals
from world.magic.services.sanctum_lvm import sum_homecoming_value
from world.room_features.models import RoomFeatureInstance
from world.room_features.seeds import ensure_sanctum_kind

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _build_cmd(cmd_cls: type, caller: object, args: str = "") -> object:
    """Instantiate *cmd_cls*, wire *caller*, and prime ``args``/``raw_string``.

    Mirrors the harness pattern in
    ``integration_tests/pipeline/test_soul_tether_telnet_journey_e2e.py``.
    """
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


def _mock_check_success() -> object:
    """Return a fake CheckResult whose outcome tier maps to SUCCESS (success_level=1)."""
    outcome = type("Outcome", (), {"success_level": 1})()
    return type("CheckResult", (), {"outcome": outcome})()


# ---------------------------------------------------------------------------
# Journey test
# ---------------------------------------------------------------------------


class SanctumTelnetJourneyTests(TestCase):
    """All 7 CmdSanctum subverbs in one sequential journey on high-fidelity fixtures.

    Uses ``setUp`` (not ``setUpTestData``) to avoid DbHolder deepcopy flake in
    CI shards.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()

        # Seed required content for sanctum rituals and check configs.
        ensure_sanctum_kind()
        ensure_sanctum_rituals()
        ensure_magic_check_content()

        # Patch perform_check for the duration of this test; SUCCESS tier throughout.
        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_success()

        # Two resonances: R1 (installed / homecoming / purging source),
        # R2 (purging target / absorb grant type after purging).
        self.resonance_1 = ResonanceFactory(name="AbyssalJourneyR1")
        self.resonance_2 = ResonanceFactory(name="PrimalJourneyR2")

        # Shared room for the sanctum.
        self.room_profile = RoomProfileFactory()

        # --- Owner character ---
        self.owner_char = CharacterFactory(db_key="SanctumOwnerE2E")
        self.owner_sheet = CharacterSheetFactory(character=self.owner_char)
        self.owner_char.db_location = self.room_profile.objectdb
        self.owner_char.save(update_fields=["db_location"])

        # Room ownership: the owner's PRIMARY persona holds the deed.
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=self.room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=self.owner_sheet.primary_persona,
            holder_organization=None,
        )

        # --- Helper character (weaves HELPER slot; owner cannot) ---
        self.helper_char = CharacterFactory(db_key="SanctumHelperE2E")
        self.helper_sheet = CharacterSheetFactory(character=self.helper_char)
        self.helper_char.db_location = self.room_profile.objectdb
        self.helper_char.save(update_fields=["db_location"])

        # Seed R1 balance for the owner: 200 units covers homecoming (100)
        # and purging (1 required after homecoming yields 1 point).
        CharacterResonance.objects.create(
            character_sheet=self.owner_sheet,
            resonance=self.resonance_1,
            balance=200,
            lifetime_earned=200,
        )

    def tearDown(self) -> None:
        self._check_patcher.stop()

    # -----------------------------------------------------------------------

    def test_full_journey(self) -> None:
        """Drive all 7 CmdSanctum subverbs; assert DB state after each step."""

        # ── Step 1: install ─────────────────────────────────────────────────
        # Owner consecrates the room with R1, personal ownership mode.
        cmd = _build_cmd(
            CmdSanctum,
            self.owner_char,
            f"install resonance={self.resonance_1.name} owner=personal",
        )
        cmd.func()

        sanctum = SanctumDetails.objects.filter(
            founder_character_sheet=self.owner_sheet,
        ).first()
        self.assertIsNotNone(sanctum, "Step 1 (install): SanctumDetails not created")
        self.assertEqual(sanctum.owner_mode, SanctumOwnerMode.PERSONAL)
        self.assertEqual(sanctum.resonance_type_id, self.resonance_1.pk)
        self.assertTrue(
            RoomFeatureInstance.objects.filter(room_profile=self.room_profile).exists(),
            "Step 1 (install): RoomFeatureInstance not created",
        )
        sanctum_pk = sanctum.pk

        # ── Step 2: weave helper ─────────────────────────────────────────────
        # Helper character weaves a HELPER-slot thread.
        # Owner cannot use slot=helper (SanctumWeavingHelperByOwnerError).
        cmd = _build_cmd(CmdSanctum, self.helper_char, "weave slot=helper")
        cmd.func()

        helper_thread = Thread.objects.filter(
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=sanctum,
            owner=self.helper_sheet,
            slot_kind=SanctumSlotKind.HELPER,
            retired_at__isnull=True,
        ).first()
        self.assertIsNotNone(
            helper_thread,
            "Step 2 (weave helper): HELPER Thread not created for helper sheet",
        )

        # ── Step 3: homecoming ───────────────────────────────────────────────
        # Sacrifice 100 R1 → base_gain = 100 // 100 = 1; SUCCESS × 1.0 = 1 point.
        cmd = _build_cmd(CmdSanctum, self.owner_char, "homecoming amount=100")
        cmd.func()

        homecoming_after = sum_homecoming_value(sanctum)
        self.assertGreater(
            homecoming_after,
            0,
            "Step 3 (homecoming): homecoming LVM sum did not advance",
        )
        owner_cr = CharacterResonance.objects.get(
            character_sheet=self.owner_sheet,
            resonance=self.resonance_1,
        )
        # 200 initial − 100 sacrificed = 100 remaining
        self.assertEqual(
            owner_cr.balance,
            100,
            "Step 3 (homecoming): owner R1 balance not decremented by 100",
        )

        # ── Step 4: purging ──────────────────────────────────────────────────
        # Purging cost = sum_homecoming × 1.0 = 1.
        # Owner still has 100 R1 (after homecoming), so ≥ 1. Changes type to R2.
        cmd = _build_cmd(
            CmdSanctum,
            self.owner_char,
            f"purging resonance={self.resonance_2.name} amount=1",
        )
        cmd.func()

        sanctum.refresh_from_db()
        self.assertEqual(
            sanctum.resonance_type_id,
            self.resonance_2.pk,
            "Step 4 (purging): sanctum resonance_type not changed to R2",
        )

        # ── Step 5: absorb ───────────────────────────────────────────────────
        # SanctumPendingPayout is normally created by the cron tick;
        # seed it manually here so absorb has something to drain.
        SanctumPendingPayout.objects.create(
            sanctum=sanctum,
            weaver_character_sheet=self.owner_sheet,
            pending_weaving=15,
            pending_owner_bonus=5,
        )
        cmd = _build_cmd(CmdSanctum, self.owner_char, "absorb")
        cmd.func()

        payout = SanctumPendingPayout.objects.get(
            sanctum=sanctum,
            weaver_character_sheet=self.owner_sheet,
        )
        self.assertEqual(
            payout.total_pending(),
            0,
            "Step 5 (absorb): pending pool not drained to 0",
        )
        # Owner now has a R2 CharacterResonance row (grant_resonance creates it).
        self.assertTrue(
            CharacterResonance.objects.filter(
                character_sheet=self.owner_sheet,
                resonance=self.resonance_2,
            ).exists(),
            "Step 5 (absorb): R2 CharacterResonance not created for owner",
        )

        # ── Step 6: sever ────────────────────────────────────────────────────
        # Helper severs their own thread by pk.
        cmd = _build_cmd(
            CmdSanctum,
            self.helper_char,
            f"sever thread={helper_thread.pk}",
        )
        cmd.func()

        helper_thread.refresh_from_db()
        self.assertIsNotNone(
            helper_thread.retired_at,
            "Step 6 (sever): helper thread not soft-retired",
        )

        # ── Step 7: dissolve ─────────────────────────────────────────────────
        # Owner dissolves the sanctum; SanctumDetails + RoomFeatureInstance gone.
        feature_instance_pk = sanctum.feature_instance_id
        cmd = _build_cmd(CmdSanctum, self.owner_char, "dissolve")
        cmd.func()

        self.assertFalse(
            SanctumDetails.objects.filter(pk=sanctum_pk).exists(),
            "Step 7 (dissolve): SanctumDetails not deleted",
        )
        self.assertFalse(
            RoomFeatureInstance.objects.filter(pk=feature_instance_pk).exists(),
            "Step 7 (dissolve): RoomFeatureInstance not deleted",
        )
