"""Crowd grouping preserves distinct voices, pools, and individual opponents."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from world.combat.constants import OpponentTier
from world.scenes.cast_list_services import _group_opponents


class CastListGroupingTests(SimpleTestCase):
    def test_voice_pool_and_individual_rows_keep_their_groups(self):
        def opponent(pk, *, voice=None, pool=None, encounter=1, tier=OpponentTier.MOOK):
            return SimpleNamespace(
                pk=pk,
                voice_persona_id=voice,
                threat_pool_id=pool,
                encounter_id=encounter,
                tier=tier,
            )

        rows = [
            opponent(1, voice=7),
            opponent(2, pool=7),
            opponent(3, voice=7),
            opponent(4, pool=7),
            opponent(5, pool=7, encounter=2),
            opponent(6),
            opponent(7),
        ]
        self.assertEqual(
            [[row.pk for row in group] for group in _group_opponents(rows)],
            [[1, 3], [2, 4], [5], [6], [7]],
        )
