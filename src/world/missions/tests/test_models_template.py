"""Tests for MissionTemplate (Phase 2, Task 2.1).

A MissionTemplate is the authored mission: the static graph anchor plus
availability metadata. These tests assert factory round-trip and the two
``clean()`` invariants (level band ordering, percent_replace ≤ 100).
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.missions.constants import ArcScope
from world.missions.factories import MissionTemplateFactory
from world.missions.models import MissionTemplate
from world.stories.factories import EraFactory


class MissionTemplateModelTests(TestCase):
    """Round-trip + clean() invariants."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.era = EraFactory(name="season-one")
        cls.template = MissionTemplateFactory(
            name="The Heist",
            slug="the-heist",
            level_band_min=2,
            level_band_max=8,
            risk_tier=3,
            arc_scope=ArcScope.ORG,
            created_in_era=cls.era,
            percent_replace=25,
            cooldown=timedelta(hours=12),
        )

    def test_factory_round_trips(self) -> None:
        fetched = MissionTemplate.objects.get(pk=self.template.pk)
        self.assertEqual(fetched.name, "The Heist")
        self.assertEqual(fetched.slug, "the-heist")
        self.assertEqual(fetched.level_band_min, 2)
        self.assertEqual(fetched.level_band_max, 8)
        self.assertEqual(fetched.arc_scope, ArcScope.ORG)
        self.assertEqual(fetched.created_in_era, self.era)
        self.assertEqual(fetched.percent_replace, 25)
        self.assertEqual(fetched.cooldown, timedelta(hours=12))
        self.assertTrue(fetched.is_active)
        self.assertEqual(str(fetched), "The Heist")

    def test_level_band_min_above_max_rejected(self) -> None:
        bad = MissionTemplateFactory.build(
            slug="bad-band",
            name="Bad Band",
            level_band_min=9,
            level_band_max=4,
        )
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_percent_replace_above_100_rejected(self) -> None:
        bad = MissionTemplateFactory.build(
            slug="bad-pct",
            name="Bad Pct",
            percent_replace=150,
        )
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_era_set_null_on_era_delete(self) -> None:
        template_pk = self.template.pk
        self.era.delete()
        # SET_NULL nulls the column at the DB level; read the persisted
        # value directly (SharedMemoryModel's identity map would otherwise
        # hand back the cached in-memory FK).
        created_in_era_id = (
            MissionTemplate.objects.filter(pk=template_pk)
            .values_list("created_in_era_id", flat=True)
            .first()
        )
        self.assertIsNone(created_in_era_id)
