"""Tests for the CourtGrantConfig singleton (#1718)."""

from django.test import TestCase

from world.covenants.models import CourtGrantConfig
from world.covenants.services import get_court_grant_config


class CourtGrantConfigTests(TestCase):
    def test_get_or_creates_singleton_with_defaults(self):
        cfg = get_court_grant_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.base_headroom, 1)
        self.assertEqual(cfg.affection_divisor, 10)
        self.assertEqual(cfg.mission_divisor, 2)
        self.assertEqual(cfg.emergency_draw_max_bonus, 5)
        self.assertEqual(cfg.debt_repay_affection_divisor, 10)
        self.assertEqual(cfg.debt_repay_mission_divisor, 2)
        self.assertEqual(cfg.petition_failure_escalation_threshold, 3)

    def test_returns_same_row_on_second_call(self):
        first = get_court_grant_config()
        second = get_court_grant_config()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CourtGrantConfig.objects.count(), 1)
