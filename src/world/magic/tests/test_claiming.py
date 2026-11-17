"""Claiming what kindled deeds set aside (#5181): the service's arithmetic and its lines."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.exceptions import ClaimError
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ensure_canonical_affinities,
)
from world.magic.models import CharacterResonance, ResonanceGrant
from world.magic.services.claiming import (
    NOTHING_WAITING_LINE,
    claim_kindled,
    claim_lines,
    pending_claim_from,
    resolve_waiting_names,
    waiting_resonances,
)


class ClaimKindledTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        _celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.abyssal.claim_verb = "gloat"
        cls.abyssal.earn_rate_percent = 150
        cls.abyssal.save()
        cls.ruin = ResonanceFactory(name="Ruin", affinity=cls.abyssal)
        cls.wild = ResonanceFactory(name="Thorn", affinity=cls.primal)

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ruin_row = CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.ruin, kindled_unclaimed=5
        )
        self.wild_row = CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.wild, kindled_unclaimed=3
        )

    def _balance(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).balance

    def test_claims_everything_waiting_and_zeroes_the_counters(self) -> None:
        claimed = claim_kindled(self.sheet)
        self.assertEqual({c.resonance: c.amount for c in claimed}, {self.ruin: 5, self.wild: 3})
        self.ruin_row.refresh_from_db()
        self.assertEqual(self.ruin_row.kindled_unclaimed, 0)
        self.assertEqual(self.wild_row.kindled_unclaimed, 0)
        self.assertEqual(self._balance(self.ruin), 5)
        grants = ResonanceGrant.objects.filter(
            character_sheet=self.sheet, source=GainSource.KINDLED_CLAIM
        )
        self.assertEqual(sorted(g.amount for g in grants), [3, 5])

    def test_claims_only_the_named_resonances(self) -> None:
        claimed = claim_kindled(self.sheet, [self.wild])
        self.assertEqual([c.resonance for c in claimed], [self.wild])
        self.assertEqual(waiting_resonances(self.sheet)[0].resonance, self.ruin)
        self.assertEqual(self._balance(self.ruin), 0)

    def test_nothing_waiting_grants_nothing(self) -> None:
        claim_kindled(self.sheet)
        grants_before = ResonanceGrant.objects.count()
        self.assertEqual(claim_kindled(self.sheet), [])
        self.assertEqual(ResonanceGrant.objects.count(), grants_before)
        self.assertEqual(claim_lines([]), (NOTHING_WAITING_LINE,))

    def test_the_earn_rate_scales_the_claim_and_the_ledger_amount_is_returned(self) -> None:
        CharacterAuraFactory(character=self.sheet, celestial=0, primal=10, abyssal=90)
        claimed = claim_kindled(self.sheet, [self.ruin])
        # 5 waiting at the Abyssal affinity's 150% is 7, as the walkthrough has it.
        self.assertEqual(claimed[0].amount, 7)
        self.assertEqual(self._balance(self.ruin), 7)

    def test_a_claim_twice_pays_once(self) -> None:
        claim_kindled(self.sheet)
        claim_kindled(self.sheet)
        self.assertEqual(self._balance(self.ruin), 5)

    def test_lines_use_the_affinitys_verb_and_fall_back_when_blank(self) -> None:
        lines = claim_lines(claim_kindled(self.sheet))
        self.assertIn("You gloat. Your Ruin grows by 5.", lines)
        self.assertIn("You claim what was waiting. Your Thorn grows by 3.", lines)


class PendingClaimTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ruin = ResonanceFactory(name="Ruin")
        self.mercy = ResonanceFactory(name="Mercy")
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.ruin, kindled_unclaimed=4
        )
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.mercy)

    def test_no_claim_asked_means_none(self) -> None:
        self.assertIsNone(pending_claim_from(self.sheet, {}))

    def test_claim_with_no_ids_means_everything(self) -> None:
        pending = pending_claim_from(self.sheet, {"claim": True, "claim_resonance_ids": []})
        self.assertEqual(pending.resonance_ids, ())

    def test_a_named_resonance_with_nothing_waiting_is_refused(self) -> None:
        with self.assertRaises(ClaimError):
            pending_claim_from(self.sheet, {"claim": True, "claim_resonance_ids": [self.mercy.pk]})

    def test_ids_without_the_claim_flag_are_refused(self) -> None:
        with self.assertRaises(ClaimError):
            pending_claim_from(self.sheet, {"claim_resonance_ids": [self.ruin.pk]})

    def test_names_resolve_without_regard_to_case(self) -> None:
        self.assertEqual(resolve_waiting_names(self.sheet, [" RUIN "]), (self.ruin.pk,))
        with self.assertRaises(ClaimError):
            resolve_waiting_names(self.sheet, ["mercy"])
