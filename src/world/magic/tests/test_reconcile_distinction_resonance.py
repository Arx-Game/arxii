"""Tests for reconcile_distinction_resonance_grants (#1834 Task 4)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.constants import GainSource
from world.magic.factories import DistinctionResonanceGrantFactory, ResonanceFactory
from world.magic.models import CharacterResonance, ResonanceGrant
from world.magic.services.distinction_resonance import reconcile_distinction_resonance_grants


class ReconcileDistinctionResonanceGrantsTests(TestCase):
    def test_establishes_character_resonance_for_each_grant(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=0
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet.character, distinction=distinction, rank=1
        )

        reconcile_distinction_resonance_grants(character_distinction)

        self.assertTrue(
            CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists()
        )

    def test_seed_grants_rank_scaled_flat_amount(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet.character, distinction=distinction, rank=2
        )

        reconcile_distinction_resonance_grants(character_distinction)

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(cr.lifetime_earned, 20)
        grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=resonance,
        )
        self.assertEqual(grants.count(), 1)
        self.assertEqual(grants.first().amount, 20)

    def test_second_reconcile_with_no_rank_change_is_idempotent(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet.character, distinction=distinction, rank=2
        )

        reconcile_distinction_resonance_grants(character_distinction)
        reconcile_distinction_resonance_grants(character_distinction)

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(cr.lifetime_earned, 20)
        grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=resonance,
        )
        self.assertEqual(grants.count(), 1)

    def test_rank_up_tops_off_delta_only(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet.character, distinction=distinction, rank=2
        )
        reconcile_distinction_resonance_grants(character_distinction)

        character_distinction.rank = 3
        character_distinction.save(update_fields=["rank"])
        reconcile_distinction_resonance_grants(character_distinction)

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(cr.lifetime_earned, 30)
        grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=resonance,
        ).order_by("granted_at")
        self.assertEqual([g.amount for g in grants], [20, 10])

    def test_rank_down_never_debits(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet.character, distinction=distinction, rank=2
        )
        reconcile_distinction_resonance_grants(character_distinction)
        character_distinction.rank = 3
        character_distinction.save(update_fields=["rank"])
        reconcile_distinction_resonance_grants(character_distinction)

        character_distinction.rank = 1
        character_distinction.save(update_fields=["rank"])
        reconcile_distinction_resonance_grants(character_distinction)

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(cr.lifetime_earned, 30)
        grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=resonance,
        )
        self.assertEqual(grants.count(), 2)
