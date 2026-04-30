"""End-to-end integration tests for Spec D §5.1 — outfit resonance trickle pipeline.

Pipeline: build sheet + Thread on Facet + equipped item bearing Facet
→ call resonance_daily_tick → assert ResonanceGrant ledger row +
CharacterResonance balance increment.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase


def _make_tenure_backed_sheet():
    """Return a CharacterSheet anchored to a fresh RosterTenure (has an Account)."""
    from world.roster.factories import RosterTenureFactory

    tenure = RosterTenureFactory()
    return tenure.roster_entry.character_sheet


def _build_sheet_with_equipped_facet_item(
    *,
    item_quality_multiplier: str = "2.00",
    attachment_quality_multiplier: str = "3.00",
    thread_level: int = 2,
):
    """Compose a CharacterSheet with an equipped item bearing a facet and a matching Thread.

    Returns: (sheet, resonance, facet, item_facet, thread)
    """
    from world.items.constants import BodyRegion, EquipmentLayer
    from world.items.factories import (
        EquippedItemFactory,
        ItemFacetFactory,
        ItemInstanceFactory,
        ItemTemplateFactory,
        QualityTierFactory,
        TemplateSlotFactory,
    )
    from world.magic.constants import TargetKind
    from world.magic.factories import CharacterResonanceFactory, FacetFactory, ResonanceFactory
    from world.magic.models import Thread

    sheet = _make_tenure_backed_sheet()
    facet = FacetFactory()
    resonance = ResonanceFactory()

    item_quality = QualityTierFactory(stat_multiplier=Decimal(item_quality_multiplier))
    attach_quality = QualityTierFactory(stat_multiplier=Decimal(attachment_quality_multiplier))

    # ItemTemplate with a TemplateSlot so slot validation passes.
    template = ItemTemplateFactory()
    TemplateSlotFactory(
        template=template,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )

    instance = ItemInstanceFactory(template=template, quality_tier=item_quality)
    EquippedItemFactory(
        character=sheet.character,
        item_instance=instance,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    # Invalidate handler cache so it sees the newly equipped item.
    sheet.character.equipped_items.invalidate()

    item_facet = ItemFacetFactory(
        item_instance=instance,
        facet=facet,
        attachment_quality_tier=attach_quality,
    )

    thread = Thread.objects.create(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.FACET,
        target_facet=facet,
        level=thread_level,
        developed_points=0,
    )

    CharacterResonanceFactory(
        character_sheet=sheet,
        resonance=resonance,
        balance=0,
        lifetime_earned=0,
    )

    return sheet, resonance, facet, item_facet, thread


class OutfitResonanceTricklePipelineTests(TestCase):
    """Happy-path: orchestrator issues a grant for a fully-configured sheet.

    Each test method in this class calls resonance_daily_tick() once on a fresh
    DB state.  Using setUpTestData here would cause grant rows written by the
    first test to be visible in the second, so fixture composition is done
    per-class (single test method) rather than sharing a class with multiple
    mutating tests.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet, cls.resonance, cls.facet, cls.item_facet, cls.thread = (
            _build_sheet_with_equipped_facet_item(
                item_quality_multiplier="2.00",
                attachment_quality_multiplier="3.00",
                thread_level=2,
            )
        )

    def test_orchestrator_grants_resonance_to_outfit_wearing_character(self) -> None:
        """Pipeline: resonance_daily_tick → ResonanceGrant + CharacterResonance updated.

        Algorithm: base(1) × item_quality(2.0) × attach_quality(3.0) × level(2) = 12.
        """
        from world.magic.constants import GainSource
        from world.magic.models import CharacterResonance, ResonanceGrant
        from world.magic.services.gain import get_resonance_gain_config, resonance_daily_tick

        sheet = self.sheet
        item_facet = self.item_facet

        # Pre-condition: balance starts at 0.
        pre_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.resonance)
        self.assertEqual(pre_cr.balance, 0)

        summary = resonance_daily_tick()

        # Orchestrator summary reports at least 1 outfit grant.
        self.assertGreaterEqual(summary.outfit_grants_issued, 1)

        # Ledger row exists with correct source + typed FK.
        self.assertTrue(
            ResonanceGrant.objects.filter(
                character_sheet=sheet,
                source=GainSource.OUTFIT_TRICKLE,
                outfit_item_facet=item_facet,
            ).exists()
        )

        # Amount matches algorithm: base × item_q × attach_q × level.
        cfg = get_resonance_gain_config()
        base = cfg.outfit_daily_trickle_per_item_resonance
        expected_amount = int(base * Decimal("2.00") * Decimal("3.00") * 2)
        grant = ResonanceGrant.objects.get(
            character_sheet=sheet,
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
        )
        self.assertEqual(grant.amount, expected_amount)

        # Balance incremented by the grant amount.
        post_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.resonance)
        self.assertEqual(post_cr.balance, expected_amount)


class OutfitTrickleNoThreadPipelineTests(TestCase):
    """Negative path: no Thread on the Facet → orchestrator issues 0 grants."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Build the full fixture, then delete the Thread so there is no anchor.
        sheet, resonance, _facet, item_facet, thread = _build_sheet_with_equipped_facet_item()
        thread.delete()
        sheet.character.equipped_items.invalidate()
        cls.sheet = sheet
        cls.resonance = resonance
        cls.item_facet = item_facet

    def test_no_thread_on_facet_means_no_grant(self) -> None:
        """Equipped item with facet but no Thread on that facet → 0 outfit grants."""
        from world.magic.constants import GainSource
        from world.magic.models import ResonanceGrant
        from world.magic.services.gain import resonance_daily_tick

        summary = resonance_daily_tick()

        self.assertEqual(summary.outfit_grants_issued, 0)
        self.assertFalse(
            ResonanceGrant.objects.filter(
                character_sheet=self.sheet,
                source=GainSource.OUTFIT_TRICKLE,
            ).exists()
        )


class OutfitTrickleNoItemsPipelineTests(TestCase):
    """Negative path: Thread on Facet but no equipped items → 0 grants for that sheet."""

    def test_no_matching_item_means_no_grant(self) -> None:
        """Sheet with Thread but no equipped items → outfit_grants_issued == 0."""
        from world.magic.constants import GainSource, TargetKind
        from world.magic.factories import CharacterResonanceFactory, FacetFactory, ResonanceFactory
        from world.magic.models import CharacterResonance, ResonanceGrant, Thread
        from world.magic.services.gain import resonance_daily_tick

        bare_sheet = _make_tenure_backed_sheet()
        facet = FacetFactory()
        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=bare_sheet,
            resonance=resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            level=1,
            developed_points=0,
        )
        CharacterResonanceFactory(character_sheet=bare_sheet, resonance=resonance)

        resonance_daily_tick()

        # No OUTFIT_TRICKLE grants for the bare sheet.
        self.assertFalse(
            ResonanceGrant.objects.filter(
                character_sheet=bare_sheet,
                source=GainSource.OUTFIT_TRICKLE,
            ).exists()
        )

        # Balance remains 0.
        cr = CharacterResonance.objects.get(character_sheet=bare_sheet, resonance=resonance)
        self.assertEqual(cr.balance, 0)
