"""Tests for the fatigue RestAction (#1491)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.fatigue import RestAction
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.constants import REST_AP_COST
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool


class RestActionTests(TestCase):
    def setUp(self) -> None:
        FatiguePool.flush_instance_cache()
        ActionPointPool.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def _create_ap_pool(self, current: int) -> ActionPointPool:
        return ActionPointPool.objects.create(
            character=self.character,
            current=current,
            maximum=200,
        )

    def test_rest_succeeds(self) -> None:
        """Resting sets well_rested and rested_today, spends AP."""
        self._create_ap_pool(200)
        result = RestAction().run(actor=self.character)
        self.assertTrue(result.success)
        self.assertIn("rest", result.message.lower())
        pool = get_or_create_fatigue_pool(self.sheet)
        self.assertTrue(pool.well_rested)
        self.assertTrue(pool.rested_today)

    def test_rest_spends_ap(self) -> None:
        """Resting deducts the configured AP cost."""
        ap_pool = self._create_ap_pool(200)
        RestAction().run(actor=self.character)
        ap_pool.refresh_from_db()
        self.assertEqual(ap_pool.current, 200 - REST_AP_COST)

    def test_rest_fails_when_already_rested(self) -> None:
        """Cannot rest twice in one day."""
        self._create_ap_pool(200)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.rested_today = True
        pool.save()

        result = RestAction().run(actor=self.character)
        self.assertFalse(result.success)
        self.assertIn("already rested", result.message.lower())

    def test_rest_fails_with_insufficient_ap(self) -> None:
        """Cannot rest without enough AP."""
        self._create_ap_pool(REST_AP_COST - 1)
        result = RestAction().run(actor=self.character)
        self.assertFalse(result.success)
        self.assertIn("action points", result.message.lower())

    def test_rest_fails_without_sheet(self) -> None:
        """An actor with no character sheet gets a uniform failure."""
        from evennia_extensions.factories import ObjectDBFactory

        bare_object = ObjectDBFactory(db_key="Bare Object")
        result = RestAction().run(actor=bare_object)
        self.assertFalse(result.success)
        self.assertIn("active character", result.message.lower())
