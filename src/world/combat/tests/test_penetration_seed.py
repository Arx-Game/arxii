"""Tests for the penetration production-seed wiring (#767).

Covers the seed-side surfaces: trait composition on the penetration
CheckType, the penetration ModifierTarget (check-scoped via
target_check_type), and idempotency of every wire function.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.checks.models import CheckTypeTrait
from world.combat.constants import PENETRATION_CHECK_TYPE_NAME
from world.combat.factories import (
    wire_penetration_check_type,
    wire_penetration_modifier_target,
)
from world.combat.tests.penetration_helpers import _build_resolver, _ledger
from world.conditions.factories import (
    DamageSuccessLevelMultiplierFactory,
    wire_penetration_factors,
)
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.constants import CHECK_CATEGORY_NAME
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
)
from world.mechanics.models import ModifierTarget


class WirePenetrationCheckTypeTraitTests(TestCase):
    """wire_penetration_check_type() authors trait composition (#767)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_authors_willpower_and_intellect_weights(self) -> None:
        check_type = wire_penetration_check_type()
        weights = {
            ctt.trait.name: ctt.weight
            for ctt in CheckTypeTrait.objects.filter(check_type=check_type)
        }
        self.assertEqual(weights["willpower"], Decimal("1.00"))
        self.assertEqual(weights["intellect"], Decimal("0.50"))

    def test_idempotent_and_preserves_staff_edits(self) -> None:
        check_type = wire_penetration_check_type()
        # Staff retunes a weight; re-running the seed must not clobber it.
        row = CheckTypeTrait.objects.get(check_type=check_type, trait__name="willpower")
        row.weight = Decimal("2.00")
        row.save()

        wire_penetration_check_type()

        self.assertEqual(CheckTypeTrait.objects.filter(check_type=check_type).count(), 2)
        row.refresh_from_db()
        self.assertEqual(row.weight, Decimal("2.00"))


class WirePenetrationModifierTargetTests(TestCase):
    """wire_penetration_modifier_target() seeds the check-scoped target (#767)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_creates_target_linked_to_penetration_check_type(self) -> None:
        target = wire_penetration_modifier_target()
        self.assertEqual(target.name, PENETRATION_CHECK_TYPE_NAME)
        self.assertEqual(target.category.name, CHECK_CATEGORY_NAME)
        self.assertTrue(target.is_active)
        self.assertEqual(target.target_check_type.name, PENETRATION_CHECK_TYPE_NAME)
        # Reverse accessor used by collect_check_modifiers (Task 2).
        self.assertEqual(target.target_check_type.modifier_target, target)

    def test_idempotent(self) -> None:
        first = wire_penetration_modifier_target()
        second = wire_penetration_modifier_target()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ModifierTarget.objects.filter(name=PENETRATION_CHECK_TYPE_NAME).count(), 1)


class PenetrationModifierContestTests(TestCase):
    """A +penetration CharacterModifier feeds the contest end-to-end (#767)."""

    @classmethod
    def setUpTestData(cls) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Modifier Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Modifier Partial"
        )
        wire_penetration_factors()
        wire_penetration_check_type()

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_character_modifier_raises_penetration_extra_modifiers(self) -> None:
        target = wire_penetration_modifier_target()
        resolver = _build_resolver(barrier_strength=10)
        distinction = DistinctionFactory(name="Wardbreaker")
        effect = DistinctionEffectFactory(distinction=distinction, target=target, value_per_rank=3)
        source = DistinctionModifierSourceFactory(
            distinction_effect=effect,
            character_distinction=CharacterDistinctionFactory(distinction=distinction),
        )
        CharacterModifierFactory(
            character=resolver.participant.character_sheet,
            value=3,
            source=source,
            target=target,
        )

        with patch("world.combat.services.perform_check") as mock_pen:
            mock_pen.return_value = MagicMock(success_level=1)
            resolver(power=20, ledger=_ledger(20))

        self.assertEqual(mock_pen.call_args.kwargs["extra_modifiers"], 3)
