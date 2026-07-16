"""Tests for exhaustion strain -> health damage wiring (#520 Phase 5)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.constants import ActionCategory
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import StrainConfigFactory
from world.conditions.models import DamageType
from world.fatigue.constants import EXHAUSTION_DAMAGE_TYPE_NAME
from world.fatigue.models import FatiguePool
from world.fatigue.services import (
    apply_exhaustion_damage,
    apply_technique_fatigue,
    get_or_create_fatigue_pool,
    resolve_fatigue_collapse,
    tick_fatigue_collapse_for_targets,
)
from world.fatigue.tests import setup_stat
from world.traits.models import TraitCategory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import tick_round_for_targets

_ENDURANCE = "world.fatigue.services.attempt_endurance_check"
_POWER_THROUGH = "world.fatigue.services.attempt_power_through"


class ApplyExhaustionDamageTests(TestCase):
    """apply_exhaustion_damage decrements health and routes through the damage pipeline."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet, health=100, max_health=100, base_max_health=100
        )

    def test_reduces_health_by_amount(self):
        """Strain damage is subtracted from current health."""
        apply_exhaustion_damage(self.sheet, 7)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 93)

    def test_authors_exhaustion_damage_type(self):
        """The 'exhaustion' DamageType is created on demand (get_or_create)."""
        self.assertFalse(DamageType.objects.filter(name=EXHAUSTION_DAMAGE_TYPE_NAME).exists())
        apply_exhaustion_damage(self.sheet, 3)
        self.assertTrue(DamageType.objects.filter(name=EXHAUSTION_DAMAGE_TYPE_NAME).exists())

    def test_zero_or_negative_amount_is_noop(self):
        """Non-positive strain leaves health untouched."""
        apply_exhaustion_damage(self.sheet, 0)
        apply_exhaustion_damage(self.sheet, -5)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 100)


class ApplyExhaustionDamageNoVitalsTests(TestCase):
    """A sheet without vitals is skipped gracefully (mirrors _deal_damage)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_missing_vitals_is_noop(self):
        """No CharacterVitals row -> no crash, no damage."""
        apply_exhaustion_damage(self.sheet, 5)  # must not raise


class ResolveFatigueCollapseTests(TestCase):
    """resolve_fatigue_collapse runs endurance + power-through and applies strain."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet, health=100, max_health=100, base_max_health=100
        )

    def test_endurance_pass_no_damage(self):
        """Passing the endurance check avoids collapse and deals no damage."""
        with patch(_ENDURANCE, return_value=True):
            result = resolve_fatigue_collapse(self.sheet, ActionCategory.PHYSICAL)
        self.assertFalse(result.collapsed)
        self.assertFalse(result.powered_through)
        self.assertEqual(result.strain_damage, 0)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 100)

    def test_both_checks_fail_collapses_and_damages(self):
        """Failing both checks collapses the character and applies strain to health."""
        with (
            patch(_ENDURANCE, return_value=False),
            patch(_POWER_THROUGH, return_value=(False, 8)),
        ):
            result = resolve_fatigue_collapse(self.sheet, ActionCategory.PHYSICAL)
        self.assertTrue(result.collapsed)
        self.assertFalse(result.powered_through)
        self.assertEqual(result.strain_damage, 8)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 92)

    def test_powerthrough_success_still_damages(self):
        """Strain damage applies even when the willpower power-through succeeds."""
        with (
            patch(_ENDURANCE, return_value=False),
            patch(_POWER_THROUGH, return_value=(True, 5)),
        ):
            result = resolve_fatigue_collapse(self.sheet, ActionCategory.PHYSICAL)
        self.assertFalse(result.collapsed)
        self.assertTrue(result.powered_through)
        self.assertEqual(result.strain_damage, 5)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 95)


class TechniqueCastCollapseCostsHealthTests(TestCase):
    """The live technique-cast path (apply_technique_fatigue) now costs health on collapse."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet, health=100, max_health=100, base_max_health=100
        )
        StrainConfigFactory()
        setup_stat(cls.sheet.character, "stamina", 10, TraitCategory.PHYSICAL)
        setup_stat(cls.sheet.character, "willpower", 10, TraitCategory.META)

    def _exhaust(self):
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current(ActionCategory.PHYSICAL, 100)  # far over capacity -> EXHAUSTED
        pool.save()
        FatiguePool.flush_instance_cache()

    def test_cast_collapse_reduces_health(self):
        """Casting while exhausted and failing collapse subtracts strain from health."""
        self._exhaust()
        with (
            patch(_ENDURANCE, return_value=False),
            patch(_POWER_THROUGH, return_value=(False, 8)),
        ):
            apply_technique_fatigue(self.sheet, ActionCategory.PHYSICAL, 4, 0)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 92)

    def test_immune_cast_does_not_cost_health(self):
        """fatigue_collapse_immune suppresses the collapse damage entirely."""
        self._exhaust()
        with (
            patch(_ENDURANCE, return_value=False),
            patch(_POWER_THROUGH, return_value=(False, 8)),
        ):
            apply_technique_fatigue(
                self.sheet, ActionCategory.PHYSICAL, 4, 0, immune_to_fatigue_collapse=True
            )
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 100)


class RoundResolutionCollapseTriggerTests(TestCase):
    """Non-cast over-capacity collapse fires on round resolution (acute tier)."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet, health=100, max_health=100, base_max_health=100
        )
        setup_stat(cls.sheet.character, "stamina", 10, TraitCategory.PHYSICAL)
        setup_stat(cls.sheet.character, "willpower", 10, TraitCategory.META)

    def _exhaust(self):
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current(ActionCategory.PHYSICAL, 100)  # far over capacity -> EXHAUSTED
        pool.save()
        FatiguePool.flush_instance_cache()

    def test_overcapacity_target_collapses_on_resolution(self):
        """An over-capacity character takes exhaustion damage at round resolution."""
        self._exhaust()
        with (
            patch(_ENDURANCE, return_value=False),
            patch(_POWER_THROUGH, return_value=(False, 6)),
        ):
            tick_fatigue_collapse_for_targets([self.sheet.character])
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 94)

    def test_round_tick_orchestrator_drives_collapse(self):
        """The vitals round-tick orchestrator invokes the fatigue collapse trigger."""
        self._exhaust()
        with (
            patch(_ENDURANCE, return_value=False),
            patch(_POWER_THROUGH, return_value=(False, 6)),
        ):
            tick_round_for_targets([self.sheet.character], timing="end")
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 94)

    def test_fresh_target_never_checks_collapse(self):
        """A character below the collapse zones is not rolled (no spurious damage)."""
        with patch(_ENDURANCE) as mock_endurance:
            tick_fatigue_collapse_for_targets([self.sheet.character])
            mock_endurance.assert_not_called()
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 100)

    def test_empty_targets_is_noop(self):
        """No participants -> no collapse evaluation (AFK-safety primitive)."""
        tick_fatigue_collapse_for_targets([])  # must not raise

    def test_non_character_target_is_skipped(self):
        """A round target with no traits handler (NPC/object) is skipped, not crashed."""

        bare = ObjectDBFactory(db_key="NPC-prop")
        CharacterVitalsFactory(
            character_sheet=CharacterSheetFactory(character=bare),
            health=100,
            max_health=100,
            base_max_health=100,
        )
        tick_fatigue_collapse_for_targets([bare])  # must not raise
