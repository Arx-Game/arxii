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
            character=sheet, distinction=distinction, rank=1
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
            character=sheet, distinction=distinction, rank=2
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
            character=sheet, distinction=distinction, rank=2
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
            character=sheet, distinction=distinction, rank=2
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

    def test_single_distinction_with_two_resonance_grants_reconciles_independently(self) -> None:
        """A distinction giving both allure AND Predatory (two grants, two resonances)."""
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        allure = ResonanceFactory()
        predatory = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=allure, flat_amount_per_rank=10
        )
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=predatory, flat_amount_per_rank=7
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet, distinction=distinction, rank=3
        )

        reconcile_distinction_resonance_grants(character_distinction)

        self.assertTrue(
            CharacterResonance.objects.filter(character_sheet=sheet, resonance=allure).exists()
        )
        self.assertTrue(
            CharacterResonance.objects.filter(character_sheet=sheet, resonance=predatory).exists()
        )

        allure_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=allure)
        predatory_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=predatory)
        self.assertEqual(allure_cr.lifetime_earned, 30)
        self.assertEqual(predatory_cr.lifetime_earned, 21)

        allure_grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=allure,
        )
        predatory_grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=predatory,
        )
        self.assertEqual(allure_grants.count(), 1)
        self.assertEqual(allure_grants.first().amount, 30)
        self.assertEqual(predatory_grants.count(), 1)
        self.assertEqual(predatory_grants.first().amount, 21)

        # Re-run: idempotent for both — no new ledger rows, no cross-contamination
        # in the already-sum filter (each is scoped to its own resonance).
        reconcile_distinction_resonance_grants(character_distinction)

        allure_cr.refresh_from_db()
        predatory_cr.refresh_from_db()
        self.assertEqual(allure_cr.lifetime_earned, 30)
        self.assertEqual(predatory_cr.lifetime_earned, 21)
        self.assertEqual(allure_grants.count(), 1)
        self.assertEqual(predatory_grants.count(), 1)

    def test_distinction_delete_survives_with_null_source_fk(self) -> None:
        """CharacterDistinction.delete() must not raise IntegrityError (#1834 review finding).

        source_character_distinction is on_delete=SET_NULL — the audit row is meant to
        survive the distinction's deletion. The res_grant_distinction_shape CheckConstraint
        previously required source_character_distinction__isnull=False whenever
        source="DISTINCTION", so the SET_NULL cascade UPDATE violated the CHECK and the
        delete raised IntegrityError. The constraint now omits that self-requirement
        (mirroring res_grant_sanctum_weaving_shape), so the ledger row survives with a
        null FK instead.
        """
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet, distinction=distinction, rank=1
        )
        reconcile_distinction_resonance_grants(character_distinction)
        grant = ResonanceGrant.objects.get(
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
            resonance=resonance,
        )

        character_distinction.delete()

        # The collector's SET_NULL cascade is a bulk raw UPDATE that bypasses the
        # idmapper identity-map cache (see AGENT memory:
        # reference-idmapper-cache-survives-collector-set-null) — flush the cache
        # before re-reading so we observe the real DB row, not the stale cached one.
        ResonanceGrant.flush_instance_cache(force=True)
        grant = ResonanceGrant.objects.get(pk=grant.pk)
        self.assertIsNone(grant.source_character_distinction)
        self.assertEqual(grant.source, GainSource.DISTINCTION)
        self.assertEqual(grant.amount, 10)

    def test_rank_down_never_debits(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet, distinction=distinction, rank=2
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
