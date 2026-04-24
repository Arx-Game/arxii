"""Tests for Spec C resonance daily + weekly tick services."""

from django.test import TestCase


class ResidenceTrickleTickTests(TestCase):
    def test_no_residence_noop(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import residence_trickle_tick

        CharacterSheetFactory()  # exists but no residence set
        summary = residence_trickle_tick()
        self.assertEqual(summary.residence_grants_issued, 0)

    def test_matching_resonance_grants_trickle(self) -> None:
        """Sheet with residence + matching aura tags gets trickle."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.magic.models import CharacterResonance
        from world.magic.services.gain import (
            get_resonance_gain_config,
            residence_trickle_tick,
            set_residence,
            tag_room_resonance,
        )

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        r_matched = ResonanceFactory()
        r_tagged_only = ResonanceFactory()

        CharacterResonanceFactory(character_sheet=sheet, resonance=r_matched)
        tag_room_resonance(rp, r_matched)
        tag_room_resonance(rp, r_tagged_only)
        set_residence(sheet, rp)

        cfg = get_resonance_gain_config()
        summary = residence_trickle_tick()

        self.assertEqual(summary.residence_grants_issued, 1)
        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=r_matched)
        self.assertEqual(cr.balance, cfg.residence_daily_trickle_per_resonance)

    def test_non_matching_skipped(self) -> None:
        """Tagged resonance != claimed resonance → 0 grants."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.magic.services.gain import (
            residence_trickle_tick,
            set_residence,
            tag_room_resonance,
        )

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        r_tagged = ResonanceFactory()
        r_claimed = ResonanceFactory()

        CharacterResonanceFactory(character_sheet=sheet, resonance=r_claimed)
        tag_room_resonance(rp, r_tagged)
        set_residence(sheet, rp)

        summary = residence_trickle_tick()
        self.assertEqual(summary.residence_grants_issued, 0)

    def test_multiple_matching_resonances(self) -> None:
        """Two matching resonances yield two grants."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.magic.services.gain import (
            residence_trickle_tick,
            set_residence,
            tag_room_resonance,
        )

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        r1 = ResonanceFactory()
        r2 = ResonanceFactory()

        CharacterResonanceFactory(character_sheet=sheet, resonance=r1)
        CharacterResonanceFactory(character_sheet=sheet, resonance=r2)
        tag_room_resonance(rp, r1)
        tag_room_resonance(rp, r2)
        set_residence(sheet, rp)

        summary = residence_trickle_tick()
        self.assertEqual(summary.residence_grants_issued, 2)


class OutfitStubTests(TestCase):
    def test_stub_returns_empty(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import get_outfit_resonance_contributions

        sheet = CharacterSheetFactory()
        result = list(get_outfit_resonance_contributions(sheet))
        self.assertEqual(result, [])

    def test_outfit_tick_returns_zero(self) -> None:
        from world.magic.services.gain import outfit_trickle_tick

        self.assertEqual(outfit_trickle_tick(), 0)


class ResonanceDailyTickTests(TestCase):
    def test_runs_with_no_sheets(self) -> None:
        from world.magic.services.gain import resonance_daily_tick

        summary = resonance_daily_tick()
        self.assertEqual(summary.residence_grants_issued, 0)
        self.assertEqual(summary.outfit_grants_issued, 0)
        self.assertEqual(summary.sheets_processed, 0)

    def test_delegates_to_residence_trickle(self) -> None:
        """Daily tick should aggregate residence trickle results."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.magic.services.gain import (
            resonance_daily_tick,
            set_residence,
            tag_room_resonance,
        )

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)
        tag_room_resonance(rp, resonance)
        set_residence(sheet, rp)

        summary = resonance_daily_tick()
        self.assertEqual(summary.residence_grants_issued, 1)
        self.assertEqual(summary.outfit_grants_issued, 0)
        self.assertEqual(summary.sheets_processed, 1)


class ResonanceWeeklySettlementTickTests(TestCase):
    def test_noop_when_no_unsettled(self) -> None:
        from world.magic.services.gain import resonance_weekly_settlement_tick

        summary = resonance_weekly_settlement_tick()
        self.assertEqual(summary.endorsers_settled, 0)
        self.assertEqual(summary.total_endorsements_settled, 0)
        self.assertEqual(summary.total_granted, 0)

    def test_settles_all_endorsers_with_unsettled(self) -> None:
        """Create 3 endorsers × 2 unsettled each → after tick, all 6 settled."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            PoseEndorsementFactory,
            ResonanceFactory,
        )
        from world.magic.models import PoseEndorsement
        from world.magic.services.gain import resonance_weekly_settlement_tick
        from world.scenes.factories import InteractionFactory

        def _make_pair(endorser):
            resonance = ResonanceFactory()
            endorsee = CharacterSheetFactory()
            CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
            PoseEndorsementFactory(
                endorser_sheet=endorser,
                endorsee_sheet=endorsee,
                interaction=InteractionFactory(),
                resonance=resonance,
            )

        endorsers = [CharacterSheetFactory() for _ in range(3)]
        for endorser in endorsers:
            _make_pair(endorser)
            _make_pair(endorser)

        self.assertEqual(PoseEndorsement.objects.filter(settled_at__isnull=True).count(), 6)

        summary = resonance_weekly_settlement_tick()
        self.assertEqual(summary.endorsers_settled, 3)
        self.assertEqual(summary.total_endorsements_settled, 6)
        self.assertEqual(PoseEndorsement.objects.filter(settled_at__isnull=True).count(), 0)
