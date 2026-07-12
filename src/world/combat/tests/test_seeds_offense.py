"""Tests for the combat offense consequence-pool flavor catalog seed (#1995).

Mirrors world/magic/tests/test_seeds_cast.py's TechniqueCastCatalogSeedTests.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import Pipeline
from world.checks.types import CheckResult, ResolutionContext
from world.combat.factories import wire_melee_attack_action_template
from world.combat.seeds_offense import (
    MELEE_OFFENSE_POOL_NAME,
    ensure_combat_offense_catalog_content,
    ensure_melee_offense_pool,
    get_melee_offense_pool,
)


class MeleeOffenseBasePoolSeedTests(TestCase):
    def test_base_pool_wired_onto_melee_attack_template(self):
        pool = ensure_melee_offense_pool()
        template = wire_melee_attack_action_template()
        self.assertEqual(template.category, "combat")
        self.assertEqual(template.pipeline, Pipeline.SINGLE)
        self.assertIsNotNone(template.consequence_pool)
        self.assertEqual(template.consequence_pool_id, pool.pk)
        self.assertEqual(template.consequence_pool.name, MELEE_OFFENSE_POOL_NAME)
        self.assertGreaterEqual(template.consequence_pool.entries.count(), 3)

    def test_idempotent_and_get_returns_same_row(self):
        a = wire_melee_attack_action_template()
        b = wire_melee_attack_action_template()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.consequence_pool_id, b.consequence_pool_id)
        self.assertEqual(get_melee_offense_pool().pk, a.consequence_pool_id)


class MeleeOffenseCatalogSeedTests(TestCase):
    def test_seeds_catalog_pools_as_children_of_base(self):
        templates = ensure_combat_offense_catalog_content()
        base_pool = get_melee_offense_pool()
        base_template = wire_melee_attack_action_template()
        self.assertEqual(len(templates), 2)
        for template in templates:
            self.assertEqual(template.check_type_id, base_template.check_type_id)
            self.assertEqual(template.pipeline, base_template.pipeline)
            self.assertEqual(template.target_type, base_template.target_type)
            self.assertEqual(template.consequence_pool.parent_id, base_pool.pk)

    def test_idempotent_no_duplicate_rows(self):
        first = ensure_combat_offense_catalog_content()
        second = ensure_combat_offense_catalog_content()
        self.assertEqual([t.pk for t in first], [t.pk for t in second])

    def test_brutal_adds_new_dramatic_consequences(self):
        ensure_combat_offense_catalog_content()
        from actions.models import ConsequencePool

        pool = ConsequencePool.objects.get(name__endswith="Brutal")
        labels = {c.label for c in pool.cached_consequences}
        self.assertIn("Overcommitted — you are wide open.", labels)
        self.assertIn("The strike lands with brutal follow-through.", labels)
        # Inherited parent consequence still present (merge, not replace).
        self.assertIn("The strike lands, but glances.", labels)

    def test_precise_overrides_parent_weights_only(self):
        ensure_combat_offense_catalog_content()
        from actions.models import ConsequencePool

        pool = ConsequencePool.objects.get(name__endswith="Precise")
        by_label = {c.label: c.weight for c in pool.cached_consequences}
        self.assertEqual(by_label["The strike lands true."], 2)
        self.assertEqual(by_label["The strike lands, but glances."], 2)
        self.assertEqual(len(by_label), 3)  # no new consequences, only overrides


class MeleeOffenseStandaloneCastProofTests(TestCase):
    """One standalone-cast proof (#1995): a PHYSICAL technique using
    'Melee Attack: Brutal' resolved through start_action_resolution selects a
    consequence from the flavored pool, not just the base pool."""

    @patch("world.checks.consequence_resolution.select_weighted")
    @patch("actions.services.perform_check")
    def test_brutal_flavor_selects_new_dramatic_consequence(
        self, mock_perform_check, mock_select_weighted
    ):
        from actions.services import start_action_resolution
        from world.checks.models import Consequence
        from world.traits.factories import CheckOutcomeFactory

        templates = ensure_combat_offense_catalog_content()
        brutal = next(t for t in templates if t.name.endswith("Brutal"))

        failure_outcome = CheckOutcomeFactory(name="Failure")
        mock_perform_check.return_value = CheckResult(
            check_type=brutal.check_type,
            outcome=failure_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        def _pick_overcommitted(items):
            return next(i for i in items if i.label == "Overcommitted — you are wide open.")

        mock_select_weighted.side_effect = _pick_overcommitted

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        resolution = start_action_resolution(character, brutal, 10, context)

        selected = Consequence.objects.get(pk=resolution.main_result.consequence_id)
        self.assertEqual(selected.label, "Overcommitted — you are wide open.")
