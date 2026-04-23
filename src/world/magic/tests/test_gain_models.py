"""Tests for Spec C gain models."""

from django.test import TestCase

from world.magic.models import ResonanceGainConfig
from world.magic.services.gain import get_resonance_gain_config


class ResonanceGainConfigTests(TestCase):
    def test_singleton_lazy_create(self) -> None:
        """get_resonance_gain_config creates the row on first call."""
        self.assertFalse(ResonanceGainConfig.objects.exists())
        cfg = get_resonance_gain_config()
        self.assertIsNotNone(cfg)
        self.assertEqual(ResonanceGainConfig.objects.count(), 1)

    def test_singleton_idempotent(self) -> None:
        cfg1 = get_resonance_gain_config()
        cfg2 = get_resonance_gain_config()
        self.assertEqual(cfg1.pk, cfg2.pk)
        self.assertEqual(ResonanceGainConfig.objects.count(), 1)

    def test_default_values(self) -> None:
        cfg = get_resonance_gain_config()
        self.assertEqual(cfg.weekly_pot_per_character, 20)
        self.assertEqual(cfg.scene_entry_grant, 4)
        self.assertEqual(cfg.residence_daily_trickle_per_resonance, 1)
        self.assertEqual(cfg.outfit_daily_trickle_per_item_resonance, 1)
        self.assertEqual(cfg.same_pair_daily_cap, 0)
        self.assertEqual(cfg.settlement_day_of_week, 0)


class AccountForSheetTests(TestCase):
    def test_returns_none_for_sheet_without_tenure(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import account_for_sheet

        sheet = CharacterSheetFactory()
        # Sheet is freshly created; no RosterEntry/RosterTenure bound.
        self.assertIsNone(account_for_sheet(sheet))

    def test_returns_account_for_played_sheet(self) -> None:
        from world.magic.services.gain import account_for_sheet
        from world.roster.factories import RosterTenureFactory

        tenure = RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        self.assertEqual(account_for_sheet(sheet), tenure.player_data.account)


class RoomAuraProfileTests(TestCase):
    def test_onetoone_to_room_profile(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.models import RoomAuraProfile

        rp = RoomProfileFactory()
        aura = RoomAuraProfile.objects.create(room_profile=rp)
        self.assertEqual(aura.pk, rp.pk)
        self.assertEqual(rp.room_aura_profile, aura)
