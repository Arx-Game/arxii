"""Atoning, accepting the changes to the aura, and cast alignment power (#5123).

Two exits from being unsettled: atone through the drift correction rite inside a live
scene (it works on lifetime, so it opens and converts even when the excess was already
spent), or accept the changes to the aura. A mixed character casts at
full alignment in every affinity that is part of who they are.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import NotUnsettledError
from world.magic.factories import (
    AuraPowerConfigFactory,
    CharacterAuraFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import CharacterResonance, DriftConversionCap, DriftConversionOffer
from world.magic.services.drift import accept_aura_change, drift_for
from world.magic.services.power_terms import ApplicableThread, PowerTermContext, aura_power_term
from world.magic.tests.test_drift_correction_rite import DriftRiteTestBase
from world.magic.tests.test_drift_offer import DriftOfferTestBase


def _set(sheet, resonance, *, balance, lifetime) -> CharacterResonance:
    row, _ = CharacterResonance.objects.get_or_create(character_sheet=sheet, resonance=resonance)
    row.balance = balance
    row.lifetime_earned = lifetime
    row.save()
    return row


def _row(sheet, resonance) -> CharacterResonance:
    return CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)


class _UnsettledOfferBase(DriftOfferTestBase):
    """A Celestial character, settled 100 percent Celestial, with 30 Abyssal on 170 Celestial."""

    def setUp(self) -> None:
        super().setUp()
        aura = self.sheet.aura_or_none
        set_aura_split(aura, celestial="100", primal="0", abyssal="0")
        _set(self.sheet, self.dawnlight, balance=0, lifetime=170)
        _set(self.sheet, self.dread, balance=30, lifetime=30)


class SpentExcessTests(_UnsettledOfferBase):
    def test_offer_opens_when_excess_was_spent(self) -> None:
        _set(self.sheet, self.dread, balance=0, lifetime=30)

        self.deed()

        self.assertTrue(drift_for(self.sheet).steps_past > 0)
        offer = DriftConversionOffer.objects.get()
        cap = DriftConversionCap.objects.get(offer=offer)
        self.assertEqual((cap.target_resonance, cap.cap), (self.dawnlight, 10))


class AtoneTests(DriftRiteTestBase):
    """Disowning the unsettling resonance: the rite atones, bounded by the cap and the excess."""

    def setUp(self) -> None:
        super().setUp()
        set_aura_split(self.sheet.aura_or_none, celestial="100", primal="0", abyssal="0")
        _set(self.sheet, self.dawnlight, balance=0, lifetime=170)
        self.cap.cap = 40
        self.cap.save()
        self.reflect_disown_dread()

    def test_atone_converts_lifetime_without_balance(self) -> None:
        _set(self.sheet, self.dread, balance=0, lifetime=30)

        self.perform()

        # The excess is 20 points (15 percent of 200 against a tolerance of 5): the cap of
        # 40 is bounded by it.
        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.balance, dread.lifetime_earned), (0, 10))
        dawn = _row(self.sheet, self.dawnlight)
        self.assertEqual((dawn.balance, dawn.lifetime_earned), (0, 190))

    def test_atone_moves_balance_only_as_far_as_it_exists(self) -> None:
        _set(self.sheet, self.dread, balance=5, lifetime=30)

        self.perform()

        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.balance, dread.lifetime_earned), (0, 10))
        dawn = _row(self.sheet, self.dawnlight)
        self.assertEqual((dawn.balance, dawn.lifetime_earned), (2, 190))

    def test_atone_that_leaves_her_settled_closes_the_offer(self) -> None:
        _set(self.sheet, self.dread, balance=0, lifetime=30)

        self.perform()

        self.assertEqual(drift_for(self.sheet).steps_past, 0)
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())
        self.assertFalse(DriftConversionCap.objects.filter(offer_id=self.offer.pk).exists())

    def test_a_weaker_roll_spends_only_its_share_of_the_cap_and_keeps_the_offer_open(self) -> None:
        _set(self.sheet, self.dread, balance=0, lifetime=30)
        self.set_shares(Success="0.25")

        self.perform()

        # int(40 x 0.25) = 10 turned; the cap falls to 30 and drift is left.
        self.assertGreater(drift_for(self.sheet).steps_past, 0)
        self.assertEqual(self.cap_value(), 30)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())


class AcceptTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.dawnlight = ResonanceFactory(name="Accept Dawnlight", affinity=cls.celestial)
        cls.dread = ResonanceFactory(name="Accept Dread", affinity=cls.abyssal)

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(self.aura, celestial="90", primal="0", abyssal="10")

    def test_accept_ends_unsettled(self) -> None:
        _set(self.sheet, self.dawnlight, balance=70, lifetime=70)
        _set(self.sheet, self.dread, balance=30, lifetime=30)
        self.assertGreater(drift_for(self.sheet).steps_past, 0)

        result = accept_aura_change(self.sheet)

        reading = drift_for(self.sheet)
        self.assertEqual(reading.steps_past, 0)
        self.assertEqual(reading.main_affinity, self.celestial)
        shares = {s.affinity_id: s.settled_percent for s in self.aura.shares.all()}
        self.assertEqual(shares, {self.celestial.pk: Decimal(70), self.abyssal.pk: Decimal(30)})
        self.assertEqual(result.settled_shares, shares)

    def test_accept_moves_a_new_main_affinity(self) -> None:
        _set(self.sheet, self.dawnlight, balance=10, lifetime=10)
        _set(self.sheet, self.dread, balance=90, lifetime=90)

        result = accept_aura_change(self.sheet)

        self.assertEqual(result.main_affinity, self.abyssal)
        self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_accept_refused_when_settled(self) -> None:
        _set(self.sheet, self.dawnlight, balance=90, lifetime=90)
        _set(self.sheet, self.dread, balance=10, lifetime=10)

        with self.assertRaises(NotUnsettledError) as raised:
            accept_aura_change(self.sheet)

        self.assertIn("not unsettled", raised.exception.user_message)

    def test_accept_writes_no_corruption(self) -> None:
        _set(self.sheet, self.dawnlight, balance=70, lifetime=70)
        _set(self.sheet, self.dread, balance=30, lifetime=30)

        accept_aura_change(self.sheet)

        for row in CharacterResonance.objects.filter(character_sheet=self.sheet):
            self.assertEqual((row.corruption_current, row.corruption_lifetime), (0, 0))

    def test_a_share_of_zero_moves_nothing_and_a_part_share_moves_part_of_the_way(self) -> None:
        _set(self.sheet, self.dawnlight, balance=70, lifetime=70)
        _set(self.sheet, self.dread, balance=30, lifetime=30)

        nothing = accept_aura_change(self.sheet, fraction=Decimal(0))
        self.assertEqual(
            nothing.settled_shares, {self.celestial.pk: Decimal(90), self.abyssal.pk: Decimal(10)}
        )
        self.assertGreater(drift_for(self.sheet).steps_past, 0)

        accept_aura_change(self.sheet, fraction=Decimal("0.5"))
        shares = {s.affinity_id: s.settled_percent for s in self.aura.shares.all()}
        # Settled began at 90/10 and the aura is 70/30, so halfway lands between them (20 in
        # Abyssal), and the shares still sum to 100.
        self.assertEqual(sum(shares.values()), Decimal(100))
        self.assertTrue(shares[self.abyssal.pk] > Decimal(10))
        self.assertTrue(shares[self.abyssal.pk] < Decimal(30))


class AcceptClosesTheOfferTests(DriftRiteTestBase):
    def test_accepting_closes_the_offer_the_character_held(self) -> None:
        self.assertGreater(drift_for(self.sheet).steps_past, 0)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

        accept_aura_change(self.sheet)

        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())
        self.assertFalse(DriftConversionCap.objects.filter(offer_id=self.offer.pk).exists())


class AlignmentPowerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.dawnlight = ResonanceFactory(name="Align Dawnlight", affinity=cls.celestial)
        cls.dread = ResonanceFactory(name="Align Dread", affinity=cls.abyssal)
        AuraPowerConfigFactory(affinity_alignment_bonus=20)

    def _caster(self, resonance, **split):
        sheet = CharacterSheetFactory()
        aura = CharacterAuraFactory(character=sheet)
        set_aura_split(aura, **{"celestial": "0", "primal": "0", "abyssal": "0", **split})
        gift = GiftFactory()
        gift.resonances.add(resonance)
        return sheet, TechniqueFactory(gift=gift)

    def _ctx(self, sheet, technique, threads=()):
        return PowerTermContext(sheet=sheet, technique=technique, applicable_threads=list(threads))

    def test_alignment_full_for_settled_minor_affinity(self) -> None:
        sheet, technique = self._caster(self.dread, celestial="70", abyssal="30")
        thread = ThreadFactory(owner=sheet, resonance=self.dread)

        pulled = aura_power_term(
            self._ctx(sheet, technique, [ApplicableThread(thread, 1, payer=self.dread)])
        )
        unpulled = aura_power_term(self._ctx(sheet, technique))

        # 30 percent of 20 would be 6; a settled share is part of who they are.
        self.assertEqual((pulled, unpulled), (20, 20))

    def test_alignment_unsettled_affinity_reads_its_current_percent(self) -> None:
        sheet, technique = self._caster(self.dread, celestial="100")
        _set(sheet, self.dawnlight, balance=70, lifetime=70)
        _set(sheet, self.dread, balance=30, lifetime=30)
        from world.magic.services.aura import recompute_aura

        recompute_aura(sheet)

        self.assertEqual(aura_power_term(self._ctx(sheet, technique)), 6)

    def test_alignment_mixed_never_exceeds_pure(self) -> None:
        pure, pure_technique = self._caster(self.dawnlight, celestial="100")
        pure_thread = ThreadFactory(owner=pure, resonance=self.dawnlight)
        mixed, mixed_technique = self._caster(self.dawnlight, celestial="60", abyssal="40")
        light = ThreadFactory(owner=mixed, resonance=self.dawnlight)
        dark = ThreadFactory(owner=mixed, resonance=self.dread)

        pure_bonus = aura_power_term(
            self._ctx(pure, pure_technique, [ApplicableThread(pure_thread, 1)])
        )
        mixed_bonus = aura_power_term(
            self._ctx(
                mixed,
                mixed_technique,
                [
                    ApplicableThread(light, 1, payer=self.dawnlight),
                    ApplicableThread(dark, 1, payer=self.dread),
                ],
            )
        )

        self.assertEqual(pure_bonus, 20)
        self.assertEqual(mixed_bonus, pure_bonus)

    def test_pulling_a_thread_paid_by_an_unsettled_minor_never_lowers_the_bonus(self) -> None:
        sheet, technique = self._caster(self.dawnlight, celestial="100")
        _set(sheet, self.dawnlight, balance=70, lifetime=70)
        _set(sheet, self.dread, balance=30, lifetime=30)
        from world.magic.services.aura import recompute_aura

        recompute_aura(sheet)
        thread = ThreadFactory(owner=sheet, resonance=self.dread)

        unpulled = aura_power_term(self._ctx(sheet, technique))
        pulled = aura_power_term(
            self._ctx(sheet, technique, [ApplicableThread(thread, 1, payer=self.dread)])
        )

        # The gift's own (settled) Celestial gives the full bonus; the unsettled 30 percent
        # Abyssal payer would give only 6, and must not replace it.
        self.assertEqual((unpulled, pulled), (20, 20))
