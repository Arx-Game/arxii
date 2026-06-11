"""Tests for the flee production-seed wiring (#878).

Covers the seed-side surfaces: trait composition on the flee CheckType,
the flee ModifierTarget (check-scoped via target_check_type), FleeConfig
singleton wiring (pk=1, check_type, consequence_pool), five tier modifier
rows, the three starter pool consequences, and the PARTIAL-tier
success_level=-1 assertion that upholds the threshold semantics relied
upon by _resolve_flee.
"""

from decimal import Decimal

from django.test import TestCase

from world.checks.models import CheckTypeTrait
from world.combat.constants import (
    FLEE_BASE_DIFFICULTY,
    FLEE_CHECK_TYPE_NAME,
    FLEE_PARTIAL_SUCCESS_LEVEL,
)
from world.combat.factories import (
    wire_flee_check_type,
    wire_flee_config,
    wire_flee_modifier_target,
)
from world.combat.models import FleeConfig, FleeTierModifier, OpponentTier
from world.mechanics.constants import CHECK_CATEGORY_NAME
from world.mechanics.models import ModifierTarget


class WireFleeCheckTypeTraitTests(TestCase):
    """wire_flee_check_type() authors trait composition (#878)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_authors_agility_and_wits_weights(self) -> None:
        check_type = wire_flee_check_type()
        weights = {
            ctt.trait.name: ctt.weight
            for ctt in CheckTypeTrait.objects.filter(check_type=check_type)
        }
        self.assertEqual(weights["agility"], Decimal("1.00"))
        self.assertEqual(weights["wits"], Decimal("0.50"))

    def test_check_type_category_is_combat(self) -> None:
        check_type = wire_flee_check_type()
        self.assertEqual(check_type.category.name, "Combat")

    def test_idempotent_and_preserves_staff_edits(self) -> None:
        check_type = wire_flee_check_type()
        # Staff retunes a weight; re-running the seed must not clobber it.
        row = CheckTypeTrait.objects.get(check_type=check_type, trait__name="agility")
        row.weight = Decimal("2.00")
        row.save()

        wire_flee_check_type()

        self.assertEqual(CheckTypeTrait.objects.filter(check_type=check_type).count(), 2)
        row.refresh_from_db()
        self.assertEqual(row.weight, Decimal("2.00"))


class WireFleeModifierTargetTests(TestCase):
    """wire_flee_modifier_target() seeds the check-scoped target (#878)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_creates_target_linked_to_flee_check_type(self) -> None:
        target = wire_flee_modifier_target()
        self.assertEqual(target.name, FLEE_CHECK_TYPE_NAME)
        self.assertEqual(target.category.name, CHECK_CATEGORY_NAME)
        self.assertTrue(target.is_active)
        self.assertEqual(target.target_check_type.name, FLEE_CHECK_TYPE_NAME)
        # Reverse accessor used by collect_check_modifiers.
        self.assertEqual(target.target_check_type.modifier_target, target)

    def test_idempotent(self) -> None:
        first = wire_flee_modifier_target()
        second = wire_flee_modifier_target()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ModifierTarget.objects.filter(name=FLEE_CHECK_TYPE_NAME).count(), 1)


class WireFleeConfigTests(TestCase):
    """wire_flee_config() seeds FleeConfig, tier modifiers, and starter pool (#878)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_creates_flee_config_singleton(self) -> None:
        wire_flee_config()
        config = FleeConfig.objects.get(pk=1)
        self.assertEqual(config.check_type.name, FLEE_CHECK_TYPE_NAME)
        self.assertEqual(config.base_difficulty, FLEE_BASE_DIFFICULTY)
        self.assertIsNotNone(config.consequence_pool)

    def test_seeds_five_tier_modifiers(self) -> None:
        wire_flee_config()
        expected = {
            OpponentTier.SWARM: -5,
            OpponentTier.MOOK: 0,
            OpponentTier.ELITE: 5,
            OpponentTier.BOSS: 10,
            OpponentTier.HERO_KILLER: 20,
        }
        self.assertEqual(FleeTierModifier.objects.count(), 5)
        for tier, modifier in expected.items():
            row = FleeTierModifier.objects.get(tier=tier)
            self.assertEqual(
                row.difficulty_modifier,
                modifier,
                f"tier {tier}: expected {modifier}, got {row.difficulty_modifier}",
            )

    def test_starter_pool_has_three_consequences(self) -> None:
        config = wire_flee_config()
        pool = config.consequence_pool
        self.assertIsNotNone(pool)
        entries = pool.entries.select_related("consequence__outcome_tier").all()
        self.assertEqual(entries.count(), 3)
        labels = {e.consequence.label for e in entries}
        self.assertIn("Winded escape", labels)
        self.assertIn("Cornered", labels)
        self.assertIn("Stumbled badly", labels)

    def test_partial_tier_has_correct_success_level(self) -> None:
        """PARTIAL's outcome_tier.success_level must equal FLEE_PARTIAL_SUCCESS_LEVEL (-1).

        _resolve_flee checks ``success_level >= FLEE_PARTIAL_SUCCESS_LEVEL`` for
        escape and ``success_level <= FLEE_PARTIAL_SUCCESS_LEVEL`` for consequence
        application. The seeded PARTIAL outcome_tier must map to -1 so the
        threshold semantics hold.
        """
        config = wire_flee_config()
        pool = config.consequence_pool
        partial_entry = pool.entries.select_related("consequence__outcome_tier").get(
            consequence__label="Winded escape"
        )
        self.assertEqual(
            partial_entry.consequence.outcome_tier.success_level,
            FLEE_PARTIAL_SUCCESS_LEVEL,  # -1
        )

    def test_idempotent_and_preserves_staff_base_difficulty_edit(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        wire_flee_config()
        # Staff raises the base difficulty; re-running must not reset it.
        FleeConfig.objects.filter(pk=1).update(base_difficulty=25)
        # .filter().update() bypasses the identity map; flush so the next get()
        # reads from DB instead of returning the stale cached instance.
        idmapper_models.flush_cache()

        wire_flee_config()

        idmapper_models.flush_cache()
        config = FleeConfig.objects.get(pk=1)
        self.assertEqual(config.base_difficulty, 25)
        self.assertEqual(FleeConfig.objects.count(), 1)

    def test_idempotent_no_duplicate_tiers(self) -> None:
        wire_flee_config()
        wire_flee_config()
        self.assertEqual(FleeTierModifier.objects.count(), 5)

    def test_idempotent_no_duplicate_pool_entries(self) -> None:
        wire_flee_config()
        wire_flee_config()
        config = FleeConfig.objects.get(pk=1)
        self.assertEqual(config.consequence_pool.entries.count(), 3)

    def test_idempotent_preserves_staff_edited_partial_success_level(self) -> None:
        """Re-running wire_flee_config() must NOT clobber a staff-edited success_level.

        Documents that get_or_create(defaults=...) semantics hold deliberately:
        the partial outcome row's success_level is seeded once and left alone on
        subsequent runs, so staff can tune it without the seed fighting them.
        """
        from evennia.utils.idmapper import models as idmapper_models

        wire_flee_config()
        from world.traits.models import CheckOutcome

        name = f"{FLEE_CHECK_TYPE_NAME}_partial"
        CheckOutcome.objects.filter(name=name).update(success_level=99)
        idmapper_models.flush_cache()

        wire_flee_config()

        idmapper_models.flush_cache()
        outcome = CheckOutcome.objects.get(name=name)
        self.assertEqual(outcome.success_level, 99)
