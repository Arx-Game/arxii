"""The affinity conversion pairs required-content probe (#4751).

Staff author one `AffinityInteraction` row per ordered pair of affinities with a conversion
multiplier and type. The dashboard lists every ordered pair of distinct affinities that has no
usable row, which is what the settling rite reports to a player as "no conversion set".
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.magic.factories import ensure_conversion_pairs
from world.magic.models import AffinityInteraction


def _resolve() -> rc.ProbeResult:
    """The shipped declaration's own probe, never a hand-copied duplicate."""
    probe = next(dep.probe for dep in rc._declarations() if dep.key == "affinity-conversion-pairs")
    return probe.resolve(None)


class AffinityConversionPairsProbeTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        AffinityInteraction.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = ensure_conversion_pairs()

    def test_every_pair_authored_is_present(self) -> None:
        self.assertTrue(_resolve().present)

    def test_a_pair_with_no_rate_is_listed_by_name_and_direction(self) -> None:
        pair = AffinityInteraction.objects.get(
            source_affinity=self.primal, environment_affinity=self.celestial
        )
        pair.conversion_multiplier = None
        pair.conversion_type = ""
        pair.save(update_fields=["conversion_multiplier", "conversion_type"])
        AffinityInteraction.objects.clear_cache()

        result = _resolve()

        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Primal to Celestial",))

    def test_a_pair_with_no_row_at_all_is_listed(self) -> None:
        AffinityInteraction.objects.get(
            source_affinity=self.abyssal, environment_affinity=self.celestial
        ).delete()
        AffinityInteraction.objects.clear_cache()

        self.assertEqual(_resolve().missing, ("Abyssal to Celestial",))
