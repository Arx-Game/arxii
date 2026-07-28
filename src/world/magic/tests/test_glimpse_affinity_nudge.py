"""Tests for the Glimpse affinity nudge mechanic (#2694).

The nudge is a one-time CG-finalize adjustment: after recompute_aura sets
the aura from resonance history, TONE and TRIGGER tags with an ``affinity``
FK shift the matching affinity by a few percentage points.
"""

from decimal import Decimal

from django.test import TestCase

from world.magic.constants import GlimpseTagAxis
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterGlimpseTagFactory,
    GlimpseTagFactory,
)
from world.magic.services.glimpse import (
    GLIMPSE_AFFINITY_NUDGE_PERCENT,
    apply_glimpse_affinity_nudge,
)


class GlimpseAffinityNudgeTests(TestCase):
    """Tests for apply_glimpse_affinity_nudge."""

    def setUp(self):
        self.celestial = AffinityFactory(name="Celestial")
        self.abyssal = AffinityFactory(name="Abyssal")
        self.primal = AffinityFactory(name="Primal")

    def test_no_tags_no_change(self):
        """An aura with no Glimpse tags is untouched."""
        aura = CharacterAuraFactory(
            celestial=Decimal("10.00"),
            primal=Decimal("70.00"),
            abyssal=Decimal("20.00"),
        )
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial == Decimal("10.00")
        assert aura.primal == Decimal("70.00")
        assert aura.abyssal == Decimal("20.00")

    def test_tag_without_affinity_no_change(self):
        """A tag with affinity=None is inert."""
        aura = CharacterAuraFactory(
            celestial=Decimal("10.00"),
            primal=Decimal("70.00"),
            abyssal=Decimal("20.00"),
        )
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="no-affinity")
        # tag.affinity is None by default
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial == Decimal("10.00")
        assert aura.primal == Decimal("70.00")
        assert aura.abyssal == Decimal("20.00")

    def test_consequence_tag_no_change(self):
        """CONSEQUENCE axis tags are ignored even if they have an affinity."""
        aura = CharacterAuraFactory(
            celestial=Decimal("10.00"),
            primal=Decimal("70.00"),
            abyssal=Decimal("20.00"),
        )
        tag = GlimpseTagFactory(
            axis=GlimpseTagAxis.CONSEQUENCE, slug="destruction", affinity=self.abyssal
        )
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial == Decimal("10.00")
        assert aura.primal == Decimal("70.00")
        assert aura.abyssal == Decimal("20.00")

    def test_sensory_tag_no_change(self):
        """SENSORY axis tags are ignored."""
        aura = CharacterAuraFactory(
            celestial=Decimal("10.00"),
            primal=Decimal("70.00"),
            abyssal=Decimal("20.00"),
        )
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.SENSORY, slug="cold", affinity=self.primal)
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial == Decimal("10.00")
        assert aura.primal == Decimal("70.00")
        assert aura.abyssal == Decimal("20.00")

    def test_witness_tag_no_change(self):
        """WITNESS axis tags are ignored."""
        aura = CharacterAuraFactory(
            celestial=Decimal("10.00"),
            primal=Decimal("70.00"),
            abyssal=Decimal("20.00"),
        )
        tag = GlimpseTagFactory(
            axis=GlimpseTagAxis.WITNESS, slug="unwitnessed", affinity=self.celestial
        )
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial == Decimal("10.00")
        assert aura.primal == Decimal("70.00")
        assert aura.abyssal == Decimal("20.00")

    def test_tone_tag_nudges_celestial(self):
        """A TONE tag with affinity=Celestial shifts celestial up."""
        aura = CharacterAuraFactory(
            celestial=Decimal("33.33"),
            primal=Decimal("33.34"),
            abyssal=Decimal("33.33"),
        )
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="wonder", affinity=self.celestial)
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        nudge = Decimal(GLIMPSE_AFFINITY_NUDGE_PERCENT)
        # celestial goes up by nudge, primal and abyssal each down by nudge/2
        assert aura.celestial == (Decimal("33.33") + nudge).quantize(Decimal("0.01"))
        # sum must be 100.00
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")

    def test_trigger_tag_nudges_abyssal(self):
        """A TRIGGER tag with affinity=Abyssal shifts abyssal up."""
        aura = CharacterAuraFactory(
            celestial=Decimal("20.00"),
            primal=Decimal("60.00"),
            abyssal=Decimal("20.00"),
        )
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TRIGGER, slug="crisis", affinity=self.abyssal)
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        nudge = Decimal(GLIMPSE_AFFINITY_NUDGE_PERCENT)
        assert aura.abyssal == (Decimal("20.00") + nudge).quantize(Decimal("0.01"))
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")

    def test_tone_and_trigger_both_nudge(self):
        """A TONE tag and a TRIGGER tag both fire (different affinities).

        Nudges apply sequentially: celestial gets +3 then -1.5 (as one of
        abyssal's "others"), abyssal gets -1.5 then +3, and primal gets
        -1.5 -1.5 = -3. The sum stays at 100.00.
        """
        aura = CharacterAuraFactory(
            celestial=Decimal("33.33"),
            primal=Decimal("33.34"),
            abyssal=Decimal("33.33"),
        )
        tone_tag = GlimpseTagFactory(
            axis=GlimpseTagAxis.TONE, slug="wonder", affinity=self.celestial
        )
        trigger_tag = GlimpseTagFactory(
            axis=GlimpseTagAxis.TRIGGER, slug="crisis", affinity=self.abyssal
        )
        CharacterGlimpseTagFactory(aura=aura, tag=tone_tag)
        CharacterGlimpseTagFactory(aura=aura, tag=trigger_tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        # The key invariant: sum stays 100.00 and both nudged affinities
        # end up higher than they started.
        assert aura.celestial > Decimal("33.33")
        assert aura.abyssal > Decimal("33.33")
        assert aura.primal < Decimal("33.34")
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")

    def test_tone_and_trigger_same_affinity_stacks(self):
        """TONE and TRIGGER both nudging the same affinity stack."""
        aura = CharacterAuraFactory(
            celestial=Decimal("10.00"),
            primal=Decimal("80.00"),
            abyssal=Decimal("10.00"),
        )
        tone_tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="terror", affinity=self.abyssal)
        trigger_tag = GlimpseTagFactory(
            axis=GlimpseTagAxis.TRIGGER, slug="crisis", affinity=self.abyssal
        )
        CharacterGlimpseTagFactory(aura=aura, tag=tone_tag)
        CharacterGlimpseTagFactory(aura=aura, tag=trigger_tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        nudge = Decimal(GLIMPSE_AFFINITY_NUDGE_PERCENT)
        expected_abyssal = Decimal("10.00") + nudge * 2
        assert aura.abyssal == expected_abyssal.quantize(Decimal("0.01"))
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")

    def test_aura_percentages_sum_to_100(self):
        """After nudge, the three percentages always sum to exactly 100.00."""
        aura = CharacterAuraFactory(
            celestial=Decimal("50.00"),
            primal=Decimal("25.00"),
            abyssal=Decimal("25.00"),
        )
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="wonder", affinity=self.celestial)
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")

    def test_no_negative_percentages(self):
        """Clamping prevents any affinity from going below 0."""
        aura = CharacterAuraFactory(
            celestial=Decimal("1.00"),
            primal=Decimal("1.00"),
            abyssal=Decimal("98.00"),
        )
        # Nudge celestial up — subtracting from primal would go negative
        # without clamping.
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="wonder", affinity=self.celestial)
        CharacterGlimpseTagFactory(aura=aura, tag=tag)
        apply_glimpse_affinity_nudge(aura)
        aura.refresh_from_db()
        assert aura.celestial >= Decimal("0.00")
        assert aura.primal >= Decimal("0.00")
        assert aura.abyssal >= Decimal("0.00")
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")
