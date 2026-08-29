"""Tests for the CreatureTemplate bestiary catalog read API (#3424).

Covers the GM-only permission gate and the ``search``/``tier`` filters -- the
web sibling of the "spawn from bestiary" GM dialog. Mirrors
``world/checks/tests/test_check_type_api.py``'s shape (``CheckTypeViewSet`` is
the pattern this ViewSet was told to mirror).
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.combat.constants import OpponentTier
from world.combat.factories import (
    CreaturePhaseTemplateFactory,
    CreatureTemplateFactory,
    ThreatPoolFactory,
)
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory


class CreatureTemplateAPISetupMixin:
    @classmethod
    def setUpTestData(cls) -> None:
        cls.pool = ThreatPoolFactory(name="Goblin Raiders")
        cls.template = CreatureTemplateFactory(
            name="Gorehorn the Undying",
            tier=OpponentTier.BOSS,
            description="A gore-horned abomination.",
            threat_pool=cls.pool,
        )
        cls.phased_template = CreatureTemplateFactory(
            name="Phased Boss",
            tier=OpponentTier.BOSS,
        )
        CreaturePhaseTemplateFactory(creature_template=cls.phased_template, phase_number=1)

        cls.mook_template = CreatureTemplateFactory(
            name="Bog Rat",
            tier=OpponentTier.MOOK,
        )

        cls.gm_account = AccountFactory()
        GMProfileFactory(account=cls.gm_account, level=GMLevel.JUNIOR)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()


class CreatureTemplateAPIPermissionTests(CreatureTemplateAPISetupMixin, TestCase):
    def test_anonymous_is_refused(self) -> None:
        client = APIClient()
        response = client.get("/api/combat/creature-templates/")
        self.assertEqual(response.status_code, 403)

    def test_non_gm_player_is_refused(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.get("/api/combat/creature-templates/")
        self.assertEqual(response.status_code, 403)

    def test_gm_may_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get("/api/combat/creature-templates/")
        self.assertEqual(response.status_code, 200)

    def test_staff_may_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get("/api/combat/creature-templates/")
        self.assertEqual(response.status_code, 200)


class CreatureTemplateAPIListTests(CreatureTemplateAPISetupMixin, TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.gm_account)

    def test_template_is_listed(self) -> None:
        response = self.client.get("/api/combat/creature-templates/")
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.template.name, names)

    def test_payload_carries_no_phase_internals(self) -> None:
        """Leak-table check (#3424 spec): only a boolean has_phases signal,
        never phase count/triggers or break-bar internals."""
        response = self.client.get("/api/combat/creature-templates/")
        row = next(r for r in response.json()["results"] if r["name"] == self.phased_template.name)
        self.assertEqual(
            set(row.keys()),
            {"id", "name", "tier", "description", "has_phases", "threat_pool_name"},
        )
        self.assertTrue(row["has_phases"])

    def test_template_without_phases_reports_false(self) -> None:
        response = self.client.get("/api/combat/creature-templates/")
        row = next(r for r in response.json()["results"] if r["name"] == self.template.name)
        self.assertFalse(row["has_phases"])

    def test_threat_pool_name_surfaced(self) -> None:
        response = self.client.get("/api/combat/creature-templates/")
        row = next(r for r in response.json()["results"] if r["name"] == self.template.name)
        self.assertEqual(row["threat_pool_name"], self.pool.name)

    def test_threat_pool_name_null_when_unset(self) -> None:
        response = self.client.get("/api/combat/creature-templates/")
        row = next(r for r in response.json()["results"] if r["name"] == self.mook_template.name)
        self.assertIsNone(row["threat_pool_name"])

    def test_search_by_name_matches(self) -> None:
        response = self.client.get("/api/combat/creature-templates/", {"search": "Gorehorn"})
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.template.name, names)
        self.assertNotIn(self.mook_template.name, names)

    def test_search_by_description_matches(self) -> None:
        response = self.client.get("/api/combat/creature-templates/", {"search": "abomination"})
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.template.name, names)

    def test_search_with_no_matches_returns_empty(self) -> None:
        response = self.client.get(
            "/api/combat/creature-templates/", {"search": "zzz_no_such_creature"}
        )
        self.assertEqual(response.json()["results"], [])

    def test_tier_filter(self) -> None:
        response = self.client.get("/api/combat/creature-templates/", {"tier": OpponentTier.MOOK})
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.mook_template.name, names)
        self.assertNotIn(self.template.name, names)
