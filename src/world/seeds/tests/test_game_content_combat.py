"""Tests for the dramatic-surge content-slice seeder (#2013)."""

from django.test import TestCase

from world.combat.constants import StakesLevel
from world.combat.models import EscalationCurve, StakesEscalationModifier
from world.relationships.constants import TrackSign
from world.relationships.models import RelationshipTrack
from world.seeds.game_content.combat import seed_dramatic_surge_content


class SeedDramaticSurgeContentTests(TestCase):
    def test_seeds_relationship_tracks(self):
        seed_dramatic_surge_content()

        bond = RelationshipTrack.objects.get(name="Bond")
        rivalry = RelationshipTrack.objects.get(name="Rivalry")
        enemies = RelationshipTrack.objects.get(name="Enemies")

        self.assertEqual(bond.sign, TrackSign.POSITIVE)
        self.assertTrue(bond.fuels_escalation_spikes)
        self.assertEqual(rivalry.sign, TrackSign.NEGATIVE)
        self.assertTrue(rivalry.fuels_escalation_spikes)
        self.assertEqual(enemies.sign, TrackSign.NEGATIVE)
        self.assertTrue(enemies.fuels_escalation_spikes)

    def test_seeds_default_curve(self):
        seed_dramatic_surge_content()

        curve = EscalationCurve.objects.get(name="Standard Dramatic Escalation")
        self.assertGreater(curve.peril_spike_intensity_amount, 0)
        self.assertGreater(curve.hated_foe_spike_intensity_amount, 0)
        self.assertTrue(curve.surge_narration)

    def test_seeds_all_five_stakes_rows_with_default_curve_from_regional_up(self):
        seed_dramatic_surge_content()

        rows = {row.stakes_level: row for row in StakesEscalationModifier.objects.all()}
        self.assertEqual(set(rows), {sl.value for sl in StakesLevel})
        self.assertIsNone(rows[StakesLevel.LOCAL].default_curve)
        for level in (
            StakesLevel.REGIONAL,
            StakesLevel.NATIONAL,
            StakesLevel.CONTINENTAL,
            StakesLevel.WORLD,
        ):
            self.assertIsNotNone(rows[level].default_curve)

    def test_idempotent(self):
        seed_dramatic_surge_content()
        seed_dramatic_surge_content()

        self.assertEqual(
            EscalationCurve.objects.filter(name="Standard Dramatic Escalation").count(), 1
        )
        self.assertEqual(RelationshipTrack.objects.filter(name="Bond").count(), 1)
        self.assertEqual(StakesEscalationModifier.objects.count(), len(StakesLevel.choices))
