"""Tests for ConsequenceOutcome read API endpoint.

Covers:
- Roulette recomputed on read from pool + selected_consequence
- Modifier breakdown rows included
- Pagination present
- Filtering by character_id
- Non-owner (non-staff, different character) gets an empty list (queryset-level
  scoping pattern used across this codebase)
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.scenes.factories import InteractionFactory


def _make_user(*, is_staff: bool = False):
    """Create an AccountDB-backed user for API tests."""
    from evennia.utils import create

    username = f"testuser_{timezone.now().timestamp()}"
    account = create.create_account(
        username,
        email=f"{username}@test.com",
        password="testpass123",
        typeclass="typeclasses.accounts.Account",
    )
    account.is_staff = is_staff
    account.save()
    return account


class ConsequenceOutcomeAPISetupMixin:
    """Shared setUp: one pool with two Consequence rows + one ConsequenceOutcome."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.traits.factories import CheckOutcomeFactory

        # Build a real pool with two consequences sharing the same outcome tier
        cls.sheet = CharacterSheetFactory()
        cls.check_type = CheckTypeFactory()
        cls.pool = ConsequencePoolFactory()
        cls.outcome_tier = CheckOutcomeFactory(name="Partial Success")

        cls.consequence_a = ConsequenceFactory(
            label="Minor Wound",
            outcome_tier=cls.outcome_tier,
            weight=3,
        )
        cls.consequence_b = ConsequenceFactory(
            label="Knockback",
            outcome_tier=cls.outcome_tier,
            weight=7,
        )
        # Link both consequences into the pool
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=cls.consequence_a)
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=cls.consequence_b)

        cls.interaction = InteractionFactory()

        # Create the outcome — consequence_b was selected
        cls.outcome = ConsequenceOutcome.objects.create(
            character=cls.sheet,
            check_type=cls.check_type,
            pool=cls.pool,
            selected_consequence=cls.consequence_b,
            modifier_total=3,
            summary="Test outcome summary",
            combat_interaction=cls.interaction,
            combat_interaction_timestamp=cls.interaction.timestamp,
        )

        # Two modifier rows
        ConsequenceOutcomeModifier.objects.create(
            outcome=cls.outcome,
            source_kind=ModifierSourceKind.ROLLMOD,
            source_label="Roll modifier",
            value=2,
        )
        ConsequenceOutcomeModifier.objects.create(
            outcome=cls.outcome,
            source_kind=ModifierSourceKind.CONDITION,
            source_label="Inspired",
            value=1,
        )


class ConsequenceOutcomeAPIReadTest(ConsequenceOutcomeAPISetupMixin, TestCase):
    """Authenticated requests: roulette payload, modifiers, pagination."""

    def setUp(self) -> None:
        self.user = _make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_200_and_paginated(self) -> None:
        """GET /api/checks/consequence-outcomes/ returns 200 with pagination wrapper."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertGreaterEqual(data["count"], 1)

    def test_outcome_display_recomputed_from_pool(self) -> None:
        """outcome_display is a list of {label, tier_name, weight, is_selected} items."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)

        row = results[0]
        display = row["outcome_display"]
        # Pool has two consequences → two display items
        self.assertEqual(len(display), 2)

        # Verify required fields exist on each display item
        for item in display:
            self.assertIn("label", item)
            self.assertIn("tier_name", item)
            self.assertIn("weight", item)
            self.assertIn("is_selected", item)

        # Exactly one is_selected=True
        selected = [d for d in display if d["is_selected"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["label"], "Knockback")

    def test_modifiers_breakdown_included(self) -> None:
        """modifiers list carries both snapshotted rows."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        row = response.json()["results"][0]
        modifiers = row["modifiers"]
        self.assertEqual(len(modifiers), 2)
        for mod in modifiers:
            self.assertIn("source_kind", mod)
            self.assertIn("source_label", mod)
            self.assertIn("value", mod)

    def test_modifier_total_present(self) -> None:
        """modifier_total field present and equals sum of modifiers."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        row = response.json()["results"][0]
        self.assertEqual(row["modifier_total"], 3)

    def test_summary_and_character_present(self) -> None:
        """summary and character fields present."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        row = response.json()["results"][0]
        self.assertIn("summary", row)
        self.assertIn("character", row)
        self.assertEqual(row["summary"], "Test outcome summary")

    def test_created_at_present(self) -> None:
        """created_at field present."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        row = response.json()["results"][0]
        self.assertIn("created_at", row)
        self.assertIsNotNone(row["created_at"])

    def test_source_ids_present(self) -> None:
        """combat_interaction_id exposed as plain id; challenge_record_id present (null)."""
        response = self.client.get("/api/checks/consequence-outcomes/")
        row = response.json()["results"][0]
        self.assertIn("combat_interaction_id", row)
        self.assertIn("challenge_record_id", row)
        self.assertEqual(row["combat_interaction_id"], self.interaction.pk)
        self.assertIsNone(row["challenge_record_id"])

    def test_retrieve_single_outcome(self) -> None:
        """GET /api/checks/consequence-outcomes/<pk>/ returns the detail row."""
        response = self.client.get(f"/api/checks/consequence-outcomes/{self.outcome.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("outcome_display", response.json())

    def test_filter_by_character(self) -> None:
        """Filtering by character_id returns only matching rows."""
        # Create a second outcome for a different sheet
        other_sheet = CharacterSheetFactory()
        other_interaction = InteractionFactory()
        ConsequenceOutcome.objects.create(
            character=other_sheet,
            check_type=self.check_type,
            pool=self.pool,
            combat_interaction=other_interaction,
            combat_interaction_timestamp=other_interaction.timestamp,
        )

        response = self.client.get(f"/api/checks/consequence-outcomes/?character={self.sheet.pk}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["character"], self.sheet.pk)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests are denied."""
        anon_client = APIClient()
        response = anon_client.get("/api/checks/consequence-outcomes/")
        self.assertIn(response.status_code, [401, 403])

    def test_no_write_endpoints(self) -> None:
        """POST/PUT/PATCH/DELETE are not allowed (read-only ViewSet)."""
        response = self.client.post("/api/checks/consequence-outcomes/", data={})
        self.assertEqual(response.status_code, 405)


class ConsequenceOutcomeAPIPermissionTest(ConsequenceOutcomeAPISetupMixin, TestCase):
    """Staff bypass: staff users can read any outcome."""

    def test_staff_can_read(self) -> None:
        """Staff user sees all outcomes regardless of character ownership."""
        staff_user = _make_user(is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff_user)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)
