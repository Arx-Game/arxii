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


class OutfitTrickleTickNoItemsTests(TestCase):
    def test_outfit_tick_returns_zero_with_no_sheets(self) -> None:
        from world.magic.services.gain import outfit_trickle_tick

        self.assertEqual(outfit_trickle_tick(), 0)

    def test_outfit_tick_returns_zero_when_no_items_equipped(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import outfit_trickle_tick

        CharacterSheetFactory()
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


class OutfitDailyTrickleTests(TestCase):
    """Tests for outfit_daily_trickle_for_character (Spec D §5.1)."""

    def _build_sheet_with_equipped_facet_item(
        self,
        *,
        item_quality_multiplier: str = "2.00",
        attachment_quality_multiplier: str = "3.00",
        thread_level: int = 2,
    ):
        """Build a CharacterSheet with an equipped item bearing a facet and a matching Thread.

        Returns: (sheet, resonance, facet, item_facet, thread)
        """
        from decimal import Decimal

        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            QualityTierFactory,
        )
        from world.magic.constants import TargetKind
        from world.magic.factories import FacetFactory, ResonanceFactory
        from world.magic.models import Thread

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        facet = FacetFactory()

        item_quality = QualityTierFactory(stat_multiplier=Decimal(item_quality_multiplier))
        attach_quality = QualityTierFactory(stat_multiplier=Decimal(attachment_quality_multiplier))
        instance = ItemInstanceFactory(quality_tier=item_quality)
        item_facet = ItemFacetFactory(
            item_instance=instance,
            facet=facet,
            attachment_quality_tier=attach_quality,
        )
        EquippedItemFactory(character=sheet.character, item_instance=instance)
        # Invalidate handler cache so it sees the newly equipped item.
        sheet.character.equipped_items.invalidate()

        thread = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            level=thread_level,
            developed_points=0,
        )
        return sheet, resonance, facet, item_facet, thread

    def test_grants_resonance_when_thread_matches(self) -> None:
        """Equipped item bearing a facet + Thread on that facet → grant issued.

        Config default base=1, item_quality=2.0, attach_quality=3.0, thread_level=2
        → amount = 1 × 2 × 3 × 2 = 12.
        """
        from world.magic.constants import GainSource
        from world.magic.models import CharacterResonance, ResonanceGrant
        from world.magic.services.gain import outfit_daily_trickle_for_character

        sheet, resonance, _facet, item_facet, _thread = self._build_sheet_with_equipped_facet_item()

        grants_issued = outfit_daily_trickle_for_character(sheet)

        self.assertEqual(grants_issued, 1)
        grant = ResonanceGrant.objects.get(character_sheet=sheet, source=GainSource.OUTFIT_TRICKLE)
        self.assertEqual(grant.outfit_item_facet, item_facet)
        self.assertEqual(grant.amount, 12)  # 1 × 2.0 × 3.0 × 2 = 12

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(cr.balance, 12)

    def test_no_thread_means_no_grant(self) -> None:
        """Equipped item with facet but no Thread on that facet → no grants."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
        )
        from world.magic.factories import FacetFactory
        from world.magic.models import ResonanceGrant
        from world.magic.services.gain import outfit_daily_trickle_for_character

        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        instance = ItemInstanceFactory()
        ItemFacetFactory(item_instance=instance, facet=facet)
        EquippedItemFactory(character=sheet.character, item_instance=instance)
        sheet.character.equipped_items.invalidate()

        grants_issued = outfit_daily_trickle_for_character(sheet)

        self.assertEqual(grants_issued, 0)
        self.assertFalse(ResonanceGrant.objects.exists())

    def test_no_items_worn_means_no_grant(self) -> None:
        """Sheet has Thread on facet but no items equipped → no grants."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import TargetKind
        from world.magic.factories import FacetFactory, ResonanceFactory
        from world.magic.models import ResonanceGrant, Thread
        from world.magic.services.gain import outfit_daily_trickle_for_character

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        facet = FacetFactory()
        Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            level=1,
            developed_points=0,
        )

        grants_issued = outfit_daily_trickle_for_character(sheet)

        self.assertEqual(grants_issued, 0)
        self.assertFalse(ResonanceGrant.objects.exists())

    def test_resonance_daily_tick_counts_outfit_grants(self) -> None:
        """resonance_daily_tick() surfaces outfit grants in summary.outfit_grants_issued."""
        from world.magic.services.gain import resonance_daily_tick

        self._build_sheet_with_equipped_facet_item()

        summary = resonance_daily_tick()

        self.assertEqual(summary.outfit_grants_issued, 1)
