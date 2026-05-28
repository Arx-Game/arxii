"""Integration tests for the unified player actions endpoint.

Verifies:
1. Endpoint shape — GET /api/actions/characters/<id>/available/ returns 200
   with a paginated ``results`` list. Each entry exposes ``target_spec``,
   ``enhancements``, and ``strain`` fields (any may be null per their
   semantics — target_spec is None for SELF actions; strain is None when
   the caster lacks a CharacterAnima row; enhancements may be an empty list).
2. Old endpoint deleted — GET /api/action-requests/available/ returns 404.
3. Query budget — with a non-trivial setup (3 techniques + 5 enhancements),
   the endpoint stays within the documented relaxed budget.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.test import APIClient

from actions.factories import ActionTemplateFactory
from actions.models import ActionEnhancement
from evennia_extensions.factories import AccountFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


def _make_social_template(name: str) -> object:
    """Build a category=social ActionTemplate (surfaced via _scene_actions)."""
    return ActionTemplateFactory(
        name=name,
        category="social",
        consequence_pool=None,
    )


class UnifiedPlayerActionsEndpointShapeTests(TestCase):
    """The unified endpoint exposes target_spec, enhancements, and strain on each entry."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory()
        cls.owner_player_data = PlayerDataFactory(account=cls.owner_account)

        cls.roster_entry = RosterEntryFactory()
        cls.sheet = cls.roster_entry.character_sheet
        cls.character = cls.sheet.character
        cls.tenure = RosterTenureFactory(
            player_data=cls.owner_player_data,
            roster_entry=cls.roster_entry,
            start_date=timezone.now(),
            end_date=None,
        )

        cls.room = ObjectDB.objects.create(db_key="UnifiedActionsShapeRoom")

        # Seed a social template with a matching enhancement so an action surfaces.
        _make_social_template("Intimidate")
        cls.technique = TechniqueFactory(name="Wave of Dread", damage_profile=False)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        ActionEnhancement.objects.create(
            base_action_key="intimidate",
            variant_name="Dread Intimidate",
            source_type="technique",
            technique=cls.technique,
        )
        CharacterAnimaFactory(character=cls.character, current=8, maximum=8)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)
        self.character.db_location = self.room
        self.character.save()

    def _url(self) -> str:
        return f"/api/actions/characters/{self.character.pk}/available/"

    def test_endpoint_returns_200_with_actions_list(self) -> None:
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreater(
            len(response.data["results"]),
            0,
            "Expected at least one action in the paginated results.",
        )

    def test_each_action_exposes_target_spec_enhancements_strain_fields(self) -> None:
        """Every serialized action has target_spec, enhancements, strain keys."""
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for action in response.data["results"]:
            self.assertIn("target_spec", action)
            self.assertIn("enhancements", action)
            self.assertIn("strain", action)

    def test_old_endpoint_returns_404(self) -> None:
        """The legacy /api/action-requests/available/ endpoint was removed."""
        response = self.client.get("/api/action-requests/available/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UnifiedPlayerActionsQueryBudgetTests(TestCase):
    """The endpoint stays within the documented relaxed query budget."""

    # 3 techniques + 5 enhancements + anima + 2 templates → at the
    # endpoint level the budget includes auth/permission lookups beyond
    # the service-layer-only budget of 12 documented for
    # get_player_actions (test_get_player_actions_enhancements.py).
    #
    # 30 is a generous initial ceiling that still catches an N+1
    # regression. Tighten only with a documented justification.
    QUERY_BUDGET = 30

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory()
        cls.owner_player_data = PlayerDataFactory(account=cls.owner_account)

        cls.roster_entry = RosterEntryFactory()
        cls.sheet = cls.roster_entry.character_sheet
        cls.character = cls.sheet.character
        cls.tenure = RosterTenureFactory(
            player_data=cls.owner_player_data,
            roster_entry=cls.roster_entry,
            start_date=timezone.now(),
            end_date=None,
        )

        cls.room = ObjectDB.objects.create(db_key="UnifiedActionsBudgetRoom")

        # Three social templates (the action_keys that the enhancements link to).
        for action_key in ("intimidate", "persuade", "flirt"):
            _make_social_template(action_key.title())

        # Three techniques the character knows.
        cls.techniques = []
        for i in range(3):
            tech = TechniqueFactory(name=f"Tech {i}", damage_profile=False)
            CharacterTechniqueFactory(character=cls.sheet, technique=tech)
            cls.techniques.append(tech)

        # Five enhancements distributed across the techniques + action_keys.
        enhancement_specs = [
            ("intimidate", cls.techniques[0]),
            ("intimidate", cls.techniques[1]),
            ("persuade", cls.techniques[0]),
            ("persuade", cls.techniques[2]),
            ("flirt", cls.techniques[2]),
        ]
        for idx, (action_key, tech) in enumerate(enhancement_specs):
            ActionEnhancement.objects.create(
                base_action_key=action_key,
                variant_name=f"Enh {idx}",
                source_type="technique",
                technique=tech,
            )

        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)
        self.character.db_location = self.room
        self.character.save()

    def _url(self) -> str:
        return f"/api/actions/characters/{self.character.pk}/available/"

    def test_endpoint_query_count_within_budget(self) -> None:
        # Warm any module-level caches by issuing one untracked request first.
        self.client.get(self._url())

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self._url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data["results"]), 0)

        captured = len(ctx.captured_queries)
        self.assertLessEqual(
            captured,
            self.QUERY_BUDGET,
            f"GET available actions issued {captured} queries (budget={self.QUERY_BUDGET}): "
            f"{[q['sql'] for q in ctx.captured_queries]}",
        )
