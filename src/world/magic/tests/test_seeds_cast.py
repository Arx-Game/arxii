"""Tests for the shared standalone technique-cast seed scaffolding (#1306)."""

from django.test import TestCase

from actions.constants import Pipeline
from world.magic.seeds_cast import (
    TECHNIQUE_CAST_POOL_NAME,
    ensure_technique_cast_content,
    ensure_technique_catalog_content,
    get_standalone_cast_pool,
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


class TechniqueCastCatalogSeedTests(TestCase):
    def test_seeds_catalog_pools_as_children_of_base(self):
        templates = ensure_technique_catalog_content()
        base_pool = get_standalone_cast_pool()
        self.assertEqual(len(templates), 2)
        base_check_type_id = base_pool.action_templates.first().check_type_id
        for template in templates:
            self.assertEqual(template.check_type_id, base_check_type_id)
            self.assertEqual(template.consequence_pool.parent_id, base_pool.pk)

    def test_idempotent_no_duplicate_rows(self):
        first = ensure_technique_catalog_content()
        second = ensure_technique_catalog_content()
        self.assertEqual([t.pk for t in first], [t.pk for t in second])

    def test_wild_surge_adds_new_failure_consequence(self):
        ensure_technique_catalog_content()
        from actions.models import ConsequencePool

        pool = ConsequencePool.objects.get(name__endswith="Wild Surge")
        labels = {c.label for c in pool.cached_consequences}
        self.assertIn("The cast overloads — a dramatic backlash flares.", labels)
        # Inherited parent consequences still present (merge, not replace).
        self.assertIn("The cast lands, imperfectly.", labels)

    def test_precise_working_overrides_parent_weights_only(self):
        ensure_technique_catalog_content()
        from actions.models import ConsequencePool

        pool = ConsequencePool.objects.get(name__endswith="Precise Working")
        by_label = {c.label: c.weight for c in pool.cached_consequences}
        self.assertEqual(by_label["The cast lands cleanly."], 2)
        self.assertEqual(len(by_label), 3)  # no new consequences, only overrides
