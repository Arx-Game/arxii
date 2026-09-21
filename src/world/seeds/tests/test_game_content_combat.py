"""Tests for the dramatic-surge content-slice seeder (#2013, #3957)."""

from django.test import TestCase, override_settings

from world.combat.constants import StakesLevel
from world.combat.models import EscalationCurve, StakesEscalationModifier
from world.relationships.constants import TypeValence
from world.relationships.models import RelationshipType
from world.seeds.game_content.combat import seed_dramatic_surge_content
from world.seeds.relationship_scale import seed_relationship_scale_content


@override_settings(SEED_SAMPLE_CONTENT=True)
class SeedDramaticSurgeContentTests(TestCase):
    """``relationships.RelationshipType`` is staff-authored content (#3957);
    SEED_SAMPLE_CONTENT opts this suite into the sample-seeding path — owned by the
    ``relationship_scale`` cluster, which ``seed_dramatic_surge_content`` only reads."""

    def test_seeds_relationship_types_with_the_right_valence(self):
        seed_relationship_scale_content()
        seed_dramatic_surge_content()

        friend = RelationshipType.objects.get(name="Friend")
        rival = RelationshipType.objects.get(name="Rival")
        enemy = RelationshipType.objects.get(name="Enemy")

        self.assertEqual(friend.valence, TypeValence.WARM)
        self.assertTrue(friend.fuels_escalation_spikes)
        self.assertEqual(rival.valence, TypeValence.HOSTILE)
        self.assertTrue(rival.fuels_escalation_spikes)
        self.assertEqual(enemy.valence, TypeValence.HOSTILE)
        self.assertTrue(enemy.fuels_escalation_spikes)

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
        seed_relationship_scale_content()
        seed_dramatic_surge_content()
        seed_dramatic_surge_content()

        self.assertEqual(
            EscalationCurve.objects.filter(name="Standard Dramatic Escalation").count(), 1
        )
        self.assertEqual(RelationshipType.objects.filter(name="Friend").count(), 1)
        self.assertEqual(StakesEscalationModifier.objects.count(), len(StakesLevel.choices))
