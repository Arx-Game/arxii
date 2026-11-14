"""Atoning, accepting the changes to the aura, and cast alignment power (#5123).

Two exits from being unsettled: atone through the drift correction rite inside a live
scene (it works on lifetime, so it opens and converts even when the excess was already
spent, Mire excess first), or accept the changes to the aura. A mixed character casts at
full alignment in every affinity that is part of who they are.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from actions.definitions.accept_aura import AcceptAuraChangeAction
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
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
from world.magic.services.conversion import _convert_full, convert_resonance_amount
from world.magic.services.drift import accept_aura_change, drift_for
from world.magic.services.power_terms import ApplicableThread, PowerTermContext, aura_power_term
from world.magic.services.resonance import grant_resonance
from world.magic.tests.test_drift_correction_rite import DriftRiteTestBase
from world.magic.tests.test_drift_offer import DriftOfferTestBase


def _set(sheet, resonance, *, balance, lifetime, mire=0) -> CharacterResonance:
    row, _ = CharacterResonance.objects.get_or_create(character_sheet=sheet, resonance=resonance)
    row.balance = balance
    row.lifetime_earned = lifetime
    row.mire_lifetime = mire
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
    def setUp(self) -> None:
        super().setUp()
        set_aura_split(self.sheet.aura_or_none, celestial="100", primal="0", abyssal="0")
        _set(self.sheet, self.dawnlight, balance=0, lifetime=170)
        self.cap.cap = 40
        self.cap.save()

    def test_atone_converts_lifetime_without_balance(self) -> None:
        _set(self.sheet, self.dread, balance=0, lifetime=30)

        result = self.perform(amount=12)

        self.assertEqual((result.converted_amount, result.granted_amount), (12, 0))
        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.balance, dread.lifetime_earned), (0, 18))
        dawn = _row(self.sheet, self.dawnlight)
        self.assertEqual((dawn.balance, dawn.lifetime_earned), (0, 182))

    def test_atone_moves_balance_only_as_far_as_it_exists(self) -> None:
        _set(self.sheet, self.dread, balance=5, lifetime=30)

        result = self.perform(amount=12)

        self.assertEqual((result.converted_amount, result.granted_amount), (12, 2))
        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.balance, dread.lifetime_earned), (0, 18))
        dawn = _row(self.sheet, self.dawnlight)
        self.assertEqual((dawn.balance, dawn.lifetime_earned), (2, 182))

    def test_atone_refuses_past_the_excess(self) -> None:
        from world.magic.exceptions import DriftConversionInvalidError

        _set(self.sheet, self.dread, balance=0, lifetime=30)
        excess = drift_for(self.sheet).convertible_points(self.abyssal.pk)

        with self.assertRaises(DriftConversionInvalidError):
            self.perform(amount=excess + 1)

    def _sineater(self) -> None:
        # 60 of 180 is a third Mire: 6 points past the allowance (54) to atone for; the
        # Sineater's own 20 Abyssal stand 11.7 past a line of nothing, 14 points.
        _set(self.sheet, self.dread, balance=60, lifetime=80, mire=60)
        _set(self.sheet, self.dawnlight, balance=0, lifetime=100)

    def test_atone_converts_mire_excess_first(self) -> None:
        self._sineater()
        reading = drift_for(self.sheet)
        self.assertEqual(reading.mire_excess_points[self.abyssal.pk], 6)
        self.assertGreater(reading.own_excess_points[self.abyssal.pk], 0)

        self.perform(amount=6)

        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.lifetime_earned, dread.mire_lifetime), (74, 54))

    def test_atone_past_the_mire_excess_then_converts_own(self) -> None:
        self._sineater()

        self.perform(amount=10)

        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.lifetime_earned, dread.mire_lifetime), (70, 54))
        dawn = _row(self.sheet, self.dawnlight)
        self.assertEqual(dawn.mire_lifetime, 0)

    def test_atone_from_a_row_without_the_mire_converts_at_most_own_excess(self) -> None:
        from world.magic.exceptions import DriftConversionInvalidError

        other = ResonanceFactory(name="Atone Other Dread", affinity=self.abyssal)
        # The Mire sits in the Dread row; the player atones from the other Abyssal row.
        _set(self.sheet, self.dread, balance=60, lifetime=60, mire=60)
        _set(self.sheet, other, balance=20, lifetime=50)
        _set(self.sheet, self.dawnlight, balance=0, lifetime=60)
        self.cap.cap = 500
        self.cap.save()
        reading = drift_for(self.sheet)
        own = reading.own_excess_points[self.abyssal.pk]
        self.assertGreater(reading.mire_excess_points[self.abyssal.pk], 0)
        self.assertEqual(reading.convertible_points(self.abyssal.pk, 0), own)

        # The other row's lifetime covers the amount, so the refusal is the convertible cap.
        with self.assertRaises(DriftConversionInvalidError) as raised:
            self.perform(amount=own + 1, source=other)
        self.assertEqual(
            raised.exception.user_message, f"Only {own} of that resonance is past who you are."
        )
        self.perform(amount=own, source=other)

        self.assertEqual(_row(self.sheet, self.dread).mire_lifetime, 60)

    def test_mire_never_exceeds_lifetime_after_atone(self) -> None:
        _set(self.sheet, self.dread, balance=60, lifetime=80, mire=60)

        # A conversion that names no Mire part still never leaves Mire past lifetime.
        convert_resonance_amount(
            self.sheet,
            source_resonance=self.dread,
            target_resonance=self.dawnlight,
            amount=40,
            multiplier=Decimal(1),
            gain_source=GainSource.DRIFT_CORRECTION,
        )

        dread = _row(self.sheet, self.dread)
        self.assertEqual(dread.lifetime_earned, 40)
        self.assertLessEqual(dread.mire_lifetime, dread.lifetime_earned)


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
        self.assertEqual(result.mire_moved, 0)

    def test_accept_moves_a_new_main_affinity(self) -> None:
        _set(self.sheet, self.dawnlight, balance=10, lifetime=10)
        _set(self.sheet, self.dread, balance=90, lifetime=90)

        result = accept_aura_change(self.sheet)

        self.assertEqual(result.main_affinity, self.abyssal)
        self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_accept_sineater_past_allowance_steps_zero(self) -> None:
        _set(self.sheet, self.dawnlight, balance=100, lifetime=100)
        _set(self.sheet, self.dread, balance=60, lifetime=60, mire=60)
        self.assertGreater(drift_for(self.sheet).steps_past, 0)

        result = accept_aura_change(self.sheet)

        self.assertEqual(result.mire_moved, 60)
        dread = _row(self.sheet, self.dread)
        self.assertEqual((dread.mire_lifetime, dread.lifetime_earned), (0, 60))
        self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_accept_refused_when_settled(self) -> None:
        _set(self.sheet, self.dawnlight, balance=90, lifetime=90)
        _set(self.sheet, self.dread, balance=10, lifetime=10)

        with self.assertRaises(NotUnsettledError) as raised:
            accept_aura_change(self.sheet)

        self.assertIn("not unsettled", raised.exception.user_message)

    def test_accept_writes_no_corruption(self) -> None:
        _set(self.sheet, self.dawnlight, balance=70, lifetime=70)
        _set(self.sheet, self.dread, balance=30, lifetime=30, mire=10)

        accept_aura_change(self.sheet)

        for row in CharacterResonance.objects.filter(character_sheet=self.sheet):
            self.assertEqual((row.corruption_current, row.corruption_lifetime), (0, 0))

    def test_the_action_accepts_and_refuses_in_player_words(self) -> None:
        _set(self.sheet, self.dawnlight, balance=70, lifetime=70)
        _set(self.sheet, self.dread, balance=30, lifetime=30)
        action = AcceptAuraChangeAction()

        done = action.run(self.sheet.character)
        again = action.run(self.sheet.character)

        self.assertTrue(done.success)
        self.assertEqual(done.message, "You become more celestial.")
        self.assertFalse(again.success)
        self.assertNotIn("accepted", again.message)


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


class MireBookkeepingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.dawnlight = ResonanceFactory(name="Mire Dawnlight", affinity=cls.celestial)
        cls.dread = ResonanceFactory(name="Mire Dread", affinity=cls.abyssal)

    def test_only_a_sineating_grant_may_come_from_the_mire(self) -> None:
        sheet = CharacterSheetFactory()

        with self.assertRaises(ValueError):
            grant_resonance(sheet, self.dread, 5, source=GainSource.STAFF_GRANT, from_mire=True)

        self.assertFalse(CharacterResonance.objects.filter(character_sheet=sheet).exists())

    def test_fall_zeroes_the_mire_without_breaking_the_constraint(self) -> None:
        sheet = CharacterSheetFactory()
        row = _set(sheet, self.dread, balance=40, lifetime=60, mire=45)

        _convert_full(row, sheet, self.dawnlight, Decimal(1))

        row.refresh_from_db()
        self.assertEqual((row.balance, row.lifetime_earned, row.mire_lifetime), (0, 0, 0))
        self.assertEqual(_row(sheet, self.dawnlight).lifetime_earned, 60)
