"""Tests for recompute_aura (#1737 — deed-driven aura drift)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import AffinityFactory, CharacterAuraFactory, ResonanceFactory
from world.magic.models import CharacterAura, CharacterResonance
from world.magic.services.aura import recompute_aura


class RecomputeAuraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.celestial = AffinityFactory(name="Celestial")
        cls.abyssal = AffinityFactory(name="Abyssal")
        cls.celestial_resonance = ResonanceFactory(affinity=cls.celestial)
        cls.abyssal_resonance = ResonanceFactory(affinity=cls.abyssal)

    def test_no_aura_row_returns_none_and_does_nothing(self):
        # sheet has no CharacterAura row at all (e.g. Quiescent/NPC)
        result = recompute_aura(self.sheet)
        assert result is None
        assert not CharacterAura.objects.filter(character=self.sheet.character).exists()

    def test_zero_lifetime_earned_leaves_stored_values_untouched(self):
        CharacterAuraFactory(character=self.sheet.character)
        before = CharacterAura.objects.get(character=self.sheet.character)
        before_celestial = before.celestial
        recompute_aura(self.sheet)
        after = CharacterAura.objects.get(character=self.sheet.character)
        assert after.celestial == before_celestial

    def test_recompute_shifts_stored_percentages_toward_earned_affinity(self):
        CharacterAuraFactory(character=self.sheet.character)
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.abyssal_resonance,
            balance=50,
            lifetime_earned=50,
        )
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.celestial_resonance,
            balance=50,
            lifetime_earned=50,
        )
        drift = recompute_aura(self.sheet)
        aura = CharacterAura.objects.get(character=self.sheet.character)
        assert drift is not None
        assert float(aura.celestial) == 50.0
        assert float(aura.abyssal) == 50.0
        assert float(aura.primal) == 0.0
