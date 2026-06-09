"""Tests for MissionTemplate (Phase 2, Task 2.1).

A MissionTemplate is the authored mission: the static graph anchor plus
availability metadata. These tests assert factory round-trip and the two
``clean()`` invariants (level band ordering, percent_replace ≤ 100).
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.missions.constants import ArcScope, MissionVisibility
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
            name="Bad Band",
            level_band_min=9,
            level_band_max=4,
        )
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_percent_replace_above_100_rejected(self) -> None:
        bad = MissionTemplateFactory.build(
            name="Bad Pct",
            percent_replace=150,
        )
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_save_enforces_level_band_invariant(self) -> None:
        # Regression (I1): clean() must run on the real create()/factory
        # write path, not only via explicit full_clean(). Before the save()
        # override this silently persisted an invalid row.
        with self.assertRaises(ValidationError):
            MissionTemplateFactory(
                name="Save Bad Band",
                level_band_min=5,
                level_band_max=2,
            )

    def test_save_enforces_percent_replace_invariant(self) -> None:
        with self.assertRaises(ValidationError):
            MissionTemplateFactory(
                name="Save Bad Pct",
                percent_replace=101,
            )

    def test_factory_defaults_to_open_visibility(self) -> None:
        # The factory defaults to OPEN so the entire test suite (which
        # never specified visibility) keeps surfacing templates to
        # non-staff characters. Production templates default to
        # RESTRICTED at the MODEL level — see the next test.
        self.assertEqual(self.template.visibility, MissionVisibility.OPEN)

    def test_model_default_is_restricted(self) -> None:
        # Production-safe default (#870): new templates start RESTRICTED
        # with an empty rule — the emergent staff-only "in testing" state
        # — and the author flips visibility=OPEN (or authors a rule) when
        # ready. The factory overrides this for test ergonomics.
        bare = MissionTemplate(
            name="Bare-Default",
            summary="x",
            level_band_min=1,
            level_band_max=5,
            risk_tier=1,
            arc_scope=ArcScope.GLOBAL,
            cooldown=timedelta(hours=1),
        )
        # Don't save — the visibility default is the field default;
        # just inspect the unsaved instance's attribute.
        self.assertEqual(bare.visibility, MissionVisibility.RESTRICTED)

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
