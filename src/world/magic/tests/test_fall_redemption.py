"""Tests for the Fall / Redemption system (#1583).

Covers:
- ``grant_compromise_resonance`` — grants non-native resonance, drifts aura.
- ``convert_resonance`` — full and partial conversion, lifetime_earned transfer,
  thread re-anchoring, monotonicity.
- ``perform_fall`` — the full Fall/Redemption ceremony (eligibility, multipliers,
  irreversibility, record creation).
- Extended ``perform_atonement_rite`` — resonance conversion alongside corruption
  reduction.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.exceptions import ConversionMappingError
from world.magic.factories import (
    ResonanceFactory,
    ensure_canonical_affinities,
    ensure_conversion_pairs,
    with_corruption_at_stage,
)
from world.magic.models import (
    AffinityInteraction,
    CharacterAura,
    CharacterResonance,
    FallRedemptionRecord,
    ResonanceConversion,
    ResonanceGrant,
)
from world.magic.models.fall_redemption import (
    CompromiseActType,
    ConversionType,
)
from world.magic.services.atonement import (
    AtonementNothingToAtone,
    perform_atonement_rite,
)
from world.magic.services.aura import set_aura_shares
from world.magic.services.conversion import (
    conversion_pair,
    convert_resonance,
    get_fall_redemption_config,
)
from world.magic.services.fall_redemption import (
    grant_compromise_resonance,
    perform_fall,
)
from world.magic.services.resonance import grant_resonance
from world.magic.types import AffinityShare


def _set_aura(sheet, celestial=80, primal=10, abyssal=10):
    """Create or update a CharacterAura with given percentages."""
    aura, _ = CharacterAura.objects.get_or_create(character=sheet)
    celestial_row, primal_row, abyssal_row = ensure_canonical_affinities()
    set_aura_shares(
        aura,
        [
            AffinityShare(affinity=row, percent=Decimal(str(percent)))
            for row, percent in (
                (celestial_row, celestial),
                (primal_row, primal),
                (abyssal_row, abyssal),
            )
            if percent
        ],
    )


def _setup_affinities_and_resonances():
    """Create the three affinities (with authored conversion pairs) and one resonance each."""
    cele_aff, primal_aff, abyssal_aff = ensure_conversion_pairs()
    cele_res = ResonanceFactory(name="Bene", affinity=cele_aff)
    primal_res = ResonanceFactory(name="Praedari", affinity=primal_aff)
    abyssal_res = ResonanceFactory(name="Dissolution", affinity=abyssal_aff)
    return cele_aff, primal_aff, abyssal_aff, cele_res, primal_res, abyssal_res


def _setup_conversion_mappings(cele_res, primal_res, abyssal_res):
    """Create ResonanceConversion mappings for all paths."""
    mappings = [
        (cele_res, primal_res.affinity, primal_res),
        (cele_res, abyssal_res.affinity, abyssal_res),
        (primal_res, abyssal_res.affinity, abyssal_res),
        (primal_res, cele_res.affinity, cele_res),
        (abyssal_res, primal_res.affinity, primal_res),
        (abyssal_res, cele_res.affinity, cele_res),
    ]
    for source, target_aff, target_res in mappings:
        ResonanceConversion.objects.get_or_create(
            source_resonance=source,
            target_affinity=target_aff,
            defaults={"target_resonance": target_res},
        )


class TestGrantCompromiseResonance(TestCase):
    """grant_compromise_resonance grants non-native resonance and drifts aura."""

    def test_grants_primal_resonance_to_celestial(self):
        """A Celestial character receiving a Primal compromise grant."""
        sheet = CharacterSheetFactory()
        _, _, _, _, primal_res, _ = _setup_affinities_and_resonances()
        _set_aura(sheet, celestial=80, primal=10, abyssal=10)

        act_type = CompromiseActType.objects.create(
            name="Combat Kill",
            target_resonance=primal_res,
            amount=10,
            is_cruelty=False,
        )

        result = grant_compromise_resonance(sheet, act_type)

        self.assertEqual(result.resonance, primal_res)
        self.assertEqual(result.balance, 10)
        self.assertEqual(result.lifetime_earned, 10)

        # Aura should have drifted toward Primal
        aura = CharacterAura.objects.get(character=sheet)
        celestial_row, primal_row, _ = ensure_canonical_affinities()
        self.assertLess(aura.percent_for(celestial_row), Decimal(80))
        self.assertGreater(aura.percent_for(primal_row), Decimal(10))

    def test_grants_abyssal_resonance_from_cruelty(self):
        """A cruelty act grants Abyssal resonance."""
        sheet = CharacterSheetFactory()
        _, _, _, _, _, abyssal_res = _setup_affinities_and_resonances()
        _set_aura(sheet, celestial=80, primal=10, abyssal=10)

        act_type = CompromiseActType.objects.create(
            name="Torture",
            target_resonance=abyssal_res,
            amount=25,
            is_cruelty=True,
        )

        result = grant_compromise_resonance(sheet, act_type)

        self.assertEqual(result.resonance, abyssal_res)
        self.assertEqual(result.balance, 25)
        self.assertEqual(result.lifetime_earned, 25)

        # Check the audit row
        grant = ResonanceGrant.objects.get(resonance=abyssal_res)
        self.assertEqual(grant.source, GainSource.COMPROMISE)
        self.assertEqual(grant.amount, 25)


class TestConvertResonanceFull(TestCase):
    """Full conversion (Fall/Redemption) — transfers balance + lifetime_earned."""

    def test_celestial_to_primal_conversion(self):
        """Celestial→Primal full conversion with 1.2× multiplier."""
        sheet = CharacterSheetFactory()
        cele_aff, primal_aff, _, cele_res, primal_res, abyssal_res = (
            _setup_affinities_and_resonances()
        )
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        # Grant some Celestial resonance
        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=80, primal=10, abyssal=10)

        multiplier = conversion_pair(cele_aff, primal_aff).conversion_multiplier

        result = convert_resonance(
            sheet,
            source_affinity=cele_aff,
            target_affinity=primal_aff,
            multiplier=multiplier,
            partial=False,
        )

        self.assertEqual(len(result.converted_resonances), 1)
        conv = result.converted_resonances[0]
        self.assertEqual(conv.balance_before, 100)
        self.assertEqual(conv.balance_after, 0)
        self.assertEqual(conv.lifetime_earned_before, 100)
        self.assertEqual(conv.lifetime_earned_after, 0)
        # 100 * 1.2 = 120
        self.assertEqual(conv.granted_balance, 120)
        self.assertEqual(conv.granted_lifetime, 120)

        # Source resonance is zeroed
        source_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=cele_res)
        self.assertEqual(source_cr.balance, 0)
        self.assertEqual(source_cr.lifetime_earned, 0)

        # Target resonance has the converted amount
        target_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=primal_res)
        self.assertEqual(target_cr.balance, 120)
        self.assertEqual(target_cr.lifetime_earned, 120)

    def test_redemption_is_lossy(self):
        """Abyssal→Primal redemption with 0.7× multiplier reduces balance."""
        sheet = CharacterSheetFactory()
        _, primal_aff, abyssal_aff, cele_res, primal_res, abyssal_res = (
            _setup_affinities_and_resonances()
        )
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, abyssal_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=10, primal=10, abyssal=80)

        multiplier = conversion_pair(abyssal_aff, primal_aff).conversion_multiplier  # 0.7

        result = convert_resonance(
            sheet,
            source_affinity=abyssal_aff,
            target_affinity=primal_aff,
            multiplier=multiplier,
            partial=False,
        )

        conv = result.converted_resonances[0]
        self.assertEqual(conv.balance_before, 100)
        self.assertEqual(conv.granted_balance, 70)
        self.assertEqual(conv.granted_lifetime, 70)


class TestConvertResonancePartial(TestCase):
    """Partial conversion (Atonement) — lossy, no threads."""

    def test_partial_conversion_reduces_balance(self):
        """Atonement converts some Primal balance back to Celestial at 0.5×."""
        sheet = CharacterSheetFactory()
        cele_aff, primal_aff, _, cele_res, primal_res, abyssal_res = (
            _setup_affinities_and_resonances()
        )
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        # Grant Celestial + Primal resonance
        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=50, primal=50, abyssal=0)

        config = get_fall_redemption_config()

        result = convert_resonance(
            sheet,
            source_affinity=primal_aff,
            target_affinity=cele_aff,
            multiplier=config.penance_exchange_rate,  # 0.5
            partial=True,
            penance_amount=40,
        )

        self.assertEqual(len(result.converted_resonances), 1)
        conv = result.converted_resonances[0]
        self.assertEqual(conv.balance_before, 100)
        self.assertEqual(conv.balance_after, 60)  # 100 - 40
        # 40 * 0.5 = 20
        self.assertEqual(conv.granted_balance, 20)


class TestConversionPair(TestCase):
    """``conversion_pair`` refuses a pair that is not fully authored."""

    def test_pair_with_multiplier_and_type_is_returned(self):
        cele, primal, _ = ensure_conversion_pairs()
        pair = conversion_pair(cele, primal)
        self.assertEqual(pair.conversion_type, ConversionType.FALL)

    def test_unconverted_pair_is_a_mapping_error(self):
        cele, primal, _ = ensure_conversion_pairs()
        pair = AffinityInteraction.objects.get(source_affinity=cele, environment_affinity=primal)
        pair.conversion_type = ""
        pair.conversion_multiplier = None
        pair.save(update_fields=["conversion_type", "conversion_multiplier"])
        AffinityInteraction.objects.clear_cache()
        with self.assertRaises(ConversionMappingError):
            conversion_pair(cele, primal)

    def test_no_row_at_all_is_a_mapping_error(self):
        cele, primal, _ = ensure_canonical_affinities()
        AffinityInteraction.objects.clear_cache()
        with self.assertRaises(ConversionMappingError):
            conversion_pair(cele, primal)

    def test_half_authored_pair_is_refused_by_the_database(self):
        cele, primal, _ = ensure_conversion_pairs()
        pair = AffinityInteraction.objects.get(source_affinity=cele, environment_affinity=primal)
        self.addCleanup(pair.refresh_from_db)
        pair.conversion_type = ""
        with self.assertRaises(IntegrityError), transaction.atomic():
            pair.save(update_fields=["conversion_type"])

    def test_unconverted_pair_fall_is_a_clean_refusal(self):
        from world.magic.exceptions import FallEligibilityError

        sheet = CharacterSheetFactory()
        _, primal_aff, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)
        pair = AffinityInteraction.objects.get(
            source_affinity=cele_res.affinity, environment_affinity=primal_aff
        )
        pair.conversion_type = ""
        pair.conversion_multiplier = None
        pair.save(update_fields=["conversion_type", "conversion_multiplier"])
        AffinityInteraction.objects.clear_cache()
        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=50, primal=45, abyssal=5)
        with self.assertRaises(FallEligibilityError):
            perform_fall(sheet, target_affinity=primal_aff)


class TestPerformFall(TestCase):
    """The full Fall/Redemption ceremony."""

    def test_fall_celestial_to_primal(self):
        """Celestial Falls to Primal when Primal aura crosses threshold."""
        sheet = CharacterSheetFactory()
        _, primal_aff, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        # Make the character dominant Celestial but with high Primal drift
        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=50, primal=45, abyssal=5)

        result = perform_fall(sheet, target_affinity=primal_aff)

        self.assertEqual(result.from_affinity.name, "Celestial")
        self.assertEqual(result.to_affinity, primal_aff)
        self.assertEqual(result.conversion_type, ConversionType.FALL)

        # Record exists
        self.assertTrue(FallRedemptionRecord.objects.filter(character_sheet=sheet).exists())

        # Celestial resonance converted to Primal (1.2× = 120)
        cele_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=cele_res)
        self.assertEqual(cele_cr.balance, 0)

        primal_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=primal_res)
        # 100 (original Primal) + 120 (converted Celestial * 1.2) = 220
        self.assertEqual(primal_cr.balance, 220)

    def test_fall_eligibility_threshold_not_met(self):
        """Cannot Fall if target affinity is below threshold."""
        from world.magic.exceptions import FallEligibilityError

        sheet = CharacterSheetFactory()
        _, primal_aff, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 10, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=90, primal=5, abyssal=5)

        with self.assertRaises(FallEligibilityError):
            perform_fall(sheet, target_affinity=primal_aff)

    def test_fall_irreversible(self):
        """Cannot Fall from the same affinity to the same target twice."""
        from world.magic.exceptions import FallEligibilityError

        sheet = CharacterSheetFactory()
        _, primal_aff, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=50, primal=45, abyssal=5)

        # First Fall succeeds
        perform_fall(sheet, target_affinity=primal_aff)

        # Aura should now be Primal-dominant (after conversion)
        aura = CharacterAura.objects.get(character=sheet)
        self.assertEqual(aura.dominant_affinity.name, "Primal")

        # Second Fall from primal to primal is refused (same affinity)
        with self.assertRaises(FallEligibilityError):
            perform_fall(sheet, target_affinity=primal_aff)

    def test_redemption_abyssal_to_primal(self):
        """Abyssal character Redeems to Primal (lossy)."""
        sheet = CharacterSheetFactory()
        _, primal_aff, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, abyssal_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 50, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=5, primal=45, abyssal=50)

        result = perform_fall(sheet, target_affinity=primal_aff)

        self.assertEqual(result.conversion_type, ConversionType.REDEMPTION)

        # Abyssal resonance is zeroed, Primal gains (100 * 0.7 = 70)
        abyssal_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=abyssal_res)
        self.assertEqual(abyssal_cr.balance, 0)

        primal_cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=primal_res)
        # 50 (original) + 70 (converted 100 * 0.7) = 120
        self.assertEqual(primal_cr.balance, 120)

    def test_fall_missing_pair_is_clean_refusal(self):
        """A path with no authored conversion pair refuses with a message, not a crash."""
        from world.magic.exceptions import FallEligibilityError

        sheet = CharacterSheetFactory()
        _, primal_aff, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)
        pair = AffinityInteraction.objects.get(
            source_affinity=cele_res.affinity, environment_affinity=primal_aff
        )
        pair.conversion_multiplier = None
        pair.conversion_type = ""
        pair.save(update_fields=["conversion_multiplier", "conversion_type"])
        AffinityInteraction.objects.clear_cache()

        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=50, primal=45, abyssal=5)

        with self.assertRaises(FallEligibilityError) as ctx:
            perform_fall(sheet, target_affinity=primal_aff)
        self.assertIn("No conversion is authored", ctx.exception.user_message)
        self.assertFalse(FallRedemptionRecord.objects.filter(character_sheet=sheet).exists())


class TestExtendedAtonement(TestCase):
    """The extended Atonement Rite does both corruption reduction and resonance conversion."""

    def test_atonement_resonance_conversion_only(self):
        """Celestial with drift but no corruption gets resonance conversion."""
        sheet = CharacterSheetFactory()
        _, _, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        # Grant some Primal drift
        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 50, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=67, primal=33, abyssal=0)

        # No corruption (stage 0)
        result = perform_atonement_rite(
            performer_sheet=sheet,
            target_sheet=sheet,
            resonance=primal_res,  # the resonance being atoned for
        )

        # Corruption effect didn't fire (stage 0)
        self.assertEqual(result.amount_reduced, 0)
        # Resonance conversion did fire
        self.assertIsNotNone(result.resonance_conversion)

    def test_atonement_both_effects_fire(self):
        """Celestial with corruption AND drift gets both effects."""
        sheet = CharacterSheetFactory()
        _, _, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, primal_res, 50, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=67, primal=33, abyssal=0)

        # Set up corruption at stage 1
        with_corruption_at_stage(sheet, primal_res, stage=1)

        result = perform_atonement_rite(
            performer_sheet=sheet,
            target_sheet=sheet,
            resonance=primal_res,
        )

        # Both effects fired
        self.assertGreater(result.amount_reduced, 0)
        self.assertIsNotNone(result.resonance_conversion)

    def test_atonement_nothing_to_atone(self):
        """Celestial with no corruption and no drift raises NothingToAtone."""
        sheet = CharacterSheetFactory()
        _, _, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, cele_res, 100, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=100, primal=0, abyssal=0)

        with self.assertRaises(AtonementNothingToAtone):
            perform_atonement_rite(
                performer_sheet=sheet,
                target_sheet=sheet,
                resonance=cele_res,
            )

    def test_primal_atonement_corruption_only(self):
        """Primal performer gets corruption reduction only (no resonance conversion)."""
        sheet = CharacterSheetFactory()
        _, _, _, cele_res, primal_res, abyssal_res = _setup_affinities_and_resonances()
        _setup_conversion_mappings(cele_res, primal_res, abyssal_res)

        grant_resonance(sheet, primal_res, 50, source=GainSource.STAFF_GRANT)
        _set_aura(sheet, celestial=10, primal=80, abyssal=10)

        with_corruption_at_stage(sheet, primal_res, stage=1)

        result = perform_atonement_rite(
            performer_sheet=sheet,
            target_sheet=sheet,
            resonance=primal_res,
        )

        # Corruption reduction fired
        self.assertGreater(result.amount_reduced, 0)
        # No resonance conversion (Primal performers don't convert to Celestial)
        self.assertIsNone(result.resonance_conversion)
