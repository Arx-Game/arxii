"""Tests for aura share rows (#4681): shares, dominance, starting split, renamed rows."""

from decimal import Decimal

from django.test import TestCase

from world.character_creation.magic_writer import _glimpse
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import AffinityNotConfigured
from world.magic.factories import AffinityFactory, CharacterAuraFactory, ResonanceFactory
from world.magic.models import Affinity, CharacterAura, CharacterResonance
from world.magic.services.aura import recompute_aura, set_aura_shares, starting_aura_shares
from world.magic.types import AffinityShare


class AuraShareTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.celestial = AffinityFactory(name="Celestial")
        cls.primal = AffinityFactory(name="Primal")
        cls.abyssal = AffinityFactory(name="Abyssal")

    def setUp(self):
        Affinity.objects.clear_cache()
        self.sheet = CharacterSheetFactory()

    def _earn(self, affinity, amount):
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=ResonanceFactory(affinity=affinity),
            balance=amount,
            lifetime_earned=amount,
        )

    def test_recompute_counts_fourth_affinity(self):
        fourth = AffinityFactory(name="Umbral")
        aura = CharacterAuraFactory(character=self.sheet)
        self._earn(self.celestial, 25)
        self._earn(self.abyssal, 25)
        self._earn(fourth, 50)
        recompute_aura(self.sheet)
        aura = CharacterAura.objects.get(pk=aura.pk)
        assert aura.percent_for(fourth) == Decimal("50.00")
        assert aura.percent_for(self.celestial) == Decimal("25.00")
        assert aura.dominant_affinity == fourth

    def test_shares_sum_to_100(self):
        aura = CharacterAuraFactory(character=self.sheet)
        self._earn(self.celestial, 1)
        self._earn(self.primal, 1)
        self._earn(self.abyssal, 1)
        recompute_aura(self.sheet)
        aura = CharacterAura.objects.get(pk=aura.pk)
        assert sum(s.percent for s in aura.cached_shares) == Decimal("100.00")

    def test_set_aura_shares_fixes_rounding_and_deletes_absent(self):
        aura = CharacterAuraFactory(character=self.sheet)
        third = Decimal(100) / Decimal(3)
        set_aura_shares(
            aura,
            [
                AffinityShare(affinity=self.celestial, percent=third),
                AffinityShare(affinity=self.primal, percent=third),
                AffinityShare(affinity=self.abyssal, percent=third),
            ],
        )
        assert sum(s.percent for s in aura.cached_shares) == Decimal("100.00")
        set_aura_shares(
            aura,
            [
                AffinityShare(affinity=self.celestial, percent=Decimal(60)),
                AffinityShare(affinity=self.primal, percent=Decimal(40)),
            ],
        )
        assert aura.percent_for(self.abyssal) == Decimal(0)
        assert aura.shares.count() == 2

    def test_set_aura_shares_refuses_a_bad_total(self):
        aura = CharacterAuraFactory(character=self.sheet)
        with self.assertRaises(ValueError):
            set_aura_shares(aura, [AffinityShare(affinity=self.primal, percent=Decimal(60))])

    def test_dominant_tie_breaks_by_pk(self):
        aura = CharacterAuraFactory(
            character=self.sheet,
            celestial=Decimal(0),
            primal=Decimal("50.00"),
            abyssal=Decimal("50.00"),
        )
        lower = min(self.primal, self.abyssal, key=lambda a: a.pk)
        assert aura.dominant_affinity == lower

    def test_starting_split_follows_pick(self):
        picked = starting_aura_shares(ResonanceFactory(affinity=self.celestial))
        assert {(s.affinity, s.percent) for s in picked} == {
            (self.celestial, Decimal("80.00")),
            (self.abyssal, Decimal("20.00")),
        }
        abyssal_pick = starting_aura_shares(ResonanceFactory(affinity=self.abyssal))
        assert {(s.affinity, s.percent) for s in abyssal_pick} == {
            (self.abyssal, Decimal("80.00")),
            (self.primal, Decimal("20.00")),
        }
        no_pick = starting_aura_shares(None)
        assert {(s.affinity, s.percent) for s in no_pick} == {
            (self.primal, Decimal("80.00")),
            (self.abyssal, Decimal("20.00")),
        }

    def test_new_aura_gets_starting_split_summing_to_100(self):
        from world.character_creation.magic_writer import MagicPicks

        picks = MagicPicks(
            tradition=None,
            gift=None,
            techniques=[],
            resonance=ResonanceFactory(affinity=self.celestial),
            anima_stat=None,
            anima_skill=None,
            ritual_name="",
            account=None,
            origin="",
        )
        aura = _glimpse(self.sheet, picks)
        assert aura.percent_for(self.celestial) == Decimal("80.00")
        assert sum(s.percent for s in aura.cached_shares) == Decimal("100.00")

    def test_renamed_affinity_still_counts(self):
        aura = CharacterAuraFactory(character=self.sheet)
        self._earn(self.primal, 10)
        self.primal.name = "Wild"
        self.primal.save()
        Affinity.objects.clear_cache()
        recompute_aura(self.sheet)
        aura = CharacterAura.objects.get(pk=aura.pk)
        assert aura.percent_for(self.primal) == Decimal("100.00")
        with self.assertRaises(AffinityNotConfigured):
            Affinity.objects.get_primal_affinity()
