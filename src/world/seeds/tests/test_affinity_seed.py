"""A freshly seeded database carries the Fall/Redemption pairs and corruption coefficients (#4681).

Before the aura became per-Affinity rows these values lived in config-singleton defaults, so a
fresh database got them for free. Now only migration 0303 sets them (and it skips an empty
database), so the Big Button seed has to.
"""

from decimal import Decimal

from django.test import TestCase, override_settings

from world.magic.models.affinity import Affinity
from world.magic.models.fall_redemption import ConversionType
from world.magic.models.resonance_environment import AffinityInteraction
from world.seeds.game_content.magic import (
    _seed_affinity_interactions,
    seed_canonical_affinities,
)

_EXPECTED_PAIRS = {
    ("Celestial", "Primal"): (ConversionType.FALL, Decimal("1.20")),
    ("Celestial", "Abyssal"): (ConversionType.FALL, Decimal("1.50")),
    ("Primal", "Abyssal"): (ConversionType.FALL, Decimal("1.20")),
    ("Abyssal", "Primal"): (ConversionType.REDEMPTION, Decimal("0.70")),
    ("Primal", "Celestial"): (ConversionType.REDEMPTION, Decimal("0.70")),
    ("Abyssal", "Celestial"): (ConversionType.REDEMPTION, Decimal("0.50")),
}


@override_settings(SEED_SAMPLE_CONTENT=True)
class SeedAffinityConversionsTests(TestCase):
    maxDiff = None

    def test_fresh_seed_has_six_conversion_pairs_and_three_coefficients(self):
        seed_canonical_affinities()
        _seed_affinity_interactions()

        coefficients = dict(Affinity.objects.values_list("name", "corruption_coefficient"))
        self.assertEqual(coefficients, {"Celestial": 0, "Primal": 2, "Abyssal": 10})

        converting = {
            (p.source_affinity.name, p.environment_affinity.name): (
                p.conversion_type,
                p.conversion_multiplier,
            )
            for p in AffinityInteraction.objects.exclude(conversion_type="")
        }
        self.assertEqual(converting, _EXPECTED_PAIRS)

    def test_reseed_keeps_staff_tuned_values(self):
        seed_canonical_affinities()
        _seed_affinity_interactions()
        primal = Affinity.objects.get(name="Primal")
        primal.corruption_coefficient = 5
        primal.save()
        pair = AffinityInteraction.objects.get(
            source_affinity__name="Celestial", environment_affinity__name="Primal"
        )
        pair.conversion_multiplier = Decimal("2.00")
        pair.save()

        seed_canonical_affinities()
        _seed_affinity_interactions()

        self.assertEqual(Affinity.objects.get(name="Primal").corruption_coefficient, 5)
        pair = AffinityInteraction.objects.get(
            source_affinity__name="Celestial", environment_affinity__name="Primal"
        )
        self.assertEqual(pair.conversion_multiplier, Decimal("2.00"))
