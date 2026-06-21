"""Tests for the shared standalone technique-cast seed scaffolding (#1306)."""

from django.test import TestCase

from actions.constants import Pipeline
from world.magic.seeds_cast import (
    TECHNIQUE_CAST_POOL_NAME,
    ensure_technique_cast_content,
    get_standalone_cast_template,
)


class TechniqueCastSeedTests(TestCase):
    def test_seeds_template_with_check_and_graded_pool(self):
        template = ensure_technique_cast_content()
        self.assertEqual(template.category, "magic")
        self.assertEqual(template.pipeline, Pipeline.SINGLE)
        self.assertIsNotNone(template.check_type)
        self.assertEqual(template.consequence_pool.name, TECHNIQUE_CAST_POOL_NAME)
        self.assertGreaterEqual(template.consequence_pool.entries.count(), 3)

    def test_idempotent_and_get_returns_same_row(self):
        a = ensure_technique_cast_content()
        b = ensure_technique_cast_content()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(get_standalone_cast_template().pk, a.pk)
