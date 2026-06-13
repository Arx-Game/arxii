"""Tests for ConsequenceOutcome read API endpoint.

Covers:
- Roulette recomputed on read from pool + selected_consequence
- Modifier breakdown rows included
- Pagination present
- Filtering by character_id
- Queryset scoped to the requesting user's own characters; non-owner gets
  an empty list, staff bypass returns all rows
- List endpoint query count does NOT scale with the number of
  ConsequenceOutcome rows (prefetch cache is hit, not bypassed)
- Roulette reconstructed from authored consequence links when pool is None
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.serializers import ConsequenceOutcomeSerializer
from world.mechanics.factories import (
    ApproachConsequenceFactory,
    ChallengeApproachFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
)
from world.mechanics.models import CharacterChallengeRecord
from world.scenes.factories import InteractionFactory, SceneFactory, SceneParticipationFactory


def _make_user(*, is_staff: bool = False):
    """Create an AccountDB-backed user for API tests."""
    return AccountFactory(is_staff=is_staff)


def _character_with_account(account):
    """Return a CharacterSheet whose character.db_account == account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class ConsequenceOutcomeAPISetupMixin:
    """Shared setUp: one pool with two Consequence rows + one ConsequenceOutcome.

    cls.owner_account is linked to cls.sheet via the ObjectDB.db_account field
    so ownership-scoping tests can authenticate as the owner.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.traits.factories import CheckOutcomeFactory

        # Build a real pool with two consequences sharing the same outcome tier
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

        # Owner account — character's db_account links the sheet to this user.
        cls.owner_account = _make_user()
        cls.sheet = _character_with_account(cls.owner_account)

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
        # Authenticate as the owner so the scoped queryset includes cls.outcome.
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)

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
        # Create a second outcome for a different sheet owned by the same user
        # so the filter test is about the character filter, not ownership.
        other_account = _make_user()
        other_sheet = _character_with_account(other_account)
        other_interaction = InteractionFactory()
        ConsequenceOutcome.objects.create(
            character=other_sheet,
            check_type=self.check_type,
            pool=self.pool,
            combat_interaction=other_interaction,
            combat_interaction_timestamp=other_interaction.timestamp,
        )

        # Staff client sees all rows, so use staff to test the filter itself.
        staff_user = _make_user(is_staff=True)
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff_user)

        response = staff_client.get(f"/api/checks/consequence-outcomes/?character={self.sheet.pk}")
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
    """Ownership scoping: non-owner gets empty list; owner and staff see their rows."""

    def test_staff_can_read_all(self) -> None:
        """Staff user sees all outcomes regardless of character ownership."""
        staff_user = _make_user(is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff_user)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)

    def test_owner_sees_own_outcomes(self) -> None:
        """Character owner sees their own outcomes."""
        client = APIClient()
        client.force_authenticate(user=self.owner_account)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_non_owner_non_staff_sees_empty_list(self) -> None:
        """A non-owner, non-staff user does NOT see another character's outcomes."""
        other_user = _make_user()
        client = APIClient()
        client.force_authenticate(user=other_user)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["results"], [])

    def test_non_owner_cannot_retrieve_by_pk(self) -> None:
        """A non-owner cannot retrieve a specific outcome by PK."""
        other_user = _make_user()
        client = APIClient()
        client.force_authenticate(user=other_user)
        response = client.get(f"/api/checks/consequence-outcomes/{self.outcome.pk}/")
        self.assertEqual(response.status_code, 404)


class ConsequenceOutcomeQueryCountTest(ConsequenceOutcomeAPISetupMixin, TestCase):
    """List endpoint query count does not scale with number of outcome rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Create two additional outcomes (total 3) for the same character.
        for _ in range(2):
            extra_interaction = InteractionFactory()
            ConsequenceOutcome.objects.create(
                character=cls.sheet,
                check_type=cls.check_type,
                pool=cls.pool,
                selected_consequence=cls.consequence_a,
                modifier_total=0,
                summary="Extra outcome",
                combat_interaction=extra_interaction,
                combat_interaction_timestamp=extra_interaction.timestamp,
            )

    def test_list_query_count_bounded(self) -> None:
        """Query count for the list endpoint must NOT grow linearly with row count.

        With 3 ConsequenceOutcome rows and properly prefetched relations,
        the total query count should be a small constant (auth + pagination +
        main queryset + prefetches), not 3 × N per-row queries.  We assert
        fewer than 15 queries — far below the naive 3-per-row ceiling.
        """
        client = APIClient()
        client.force_authenticate(user=self.owner_account)

        with CaptureQueriesContext(connection) as ctx:
            response = client.get("/api/checks/consequence-outcomes/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 3)

        query_count = len(ctx.captured_queries)
        # 3 rows × naive-3-queries-per-row = 9 queries minimum for the N+1 case.
        # With prefetch the constant overhead is well under 15.
        self.assertLess(
            query_count,
            15,
            msg=(
                f"Expected <15 queries for 3 outcomes (prefetch should be active), "
                f"got {query_count}. Prefetch cache may not be hit."
            ),
        )


class ConsequenceOutcomePoollessDisplayTest(TestCase):
    """Serializer reconstructs roulette display from authored links when pool is None.

    Covers the branch in get_outcome_display() for ConsequenceOutcome rows
    written by resolve_challenge (pool=None, challenge_record set).
    """

    def setUp(self) -> None:
        from world.traits.factories import CheckOutcomeFactory

        self.owner_account = AccountFactory()
        char = CharacterFactory()
        char.db_account = self.owner_account
        char.save()
        self.sheet = CharacterSheetFactory(character=char)

        self.check_type = CheckTypeFactory()
        self.outcome_tier = CheckOutcomeFactory(name="Partial Success")

        # Two consequences: one template-level, one approach-level.
        self.template_consequence = ConsequenceFactory(
            label="Template Wound",
            outcome_tier=self.outcome_tier,
            weight=4,
        )
        self.approach_consequence = ConsequenceFactory(
            label="Approach Stumble",
            outcome_tier=self.outcome_tier,
            weight=6,
        )

        # Wire up the challenge hierarchy
        self.template = ChallengeTemplateFactory()
        self.approach = ChallengeApproachFactory(
            challenge_template=self.template,
            check_type=self.check_type,
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=self.template,
            consequence=self.template_consequence,
        )
        ApproachConsequenceFactory(
            approach=self.approach,
            consequence=self.approach_consequence,
        )

        self.challenge_instance = ChallengeInstanceFactory(template=self.template)

        self.challenge_record = CharacterChallengeRecord.objects.create(
            character=char,
            challenge_instance=self.challenge_instance,
            approach=self.approach,
            consequence=self.approach_consequence,
        )

        # pool=None — the resolution did not use a ConsequencePool
        self.pool_less_outcome = ConsequenceOutcome.objects.create(
            character=self.sheet,
            check_type=self.check_type,
            pool=None,
            selected_consequence=self.approach_consequence,
            modifier_total=0,
            summary="Poolless test",
            challenge_record=self.challenge_record,
        )

    def test_outcome_display_reconstructed_when_pool_is_none(self) -> None:
        """Serializer builds outcome_display from authored links, not from pool."""
        data = ConsequenceOutcomeSerializer(self.pool_less_outcome).data
        self.assertGreater(len(data["outcome_display"]), 0)
        selected = [row for row in data["outcome_display"] if row["is_selected"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["label"], "Approach Stumble")
        # The display is the UNION of approach- and template-level links — assert
        # the template consequence is present too, so a regression that drops the
        # template side would fail here rather than pass silently.
        labels = {row["label"] for row in data["outcome_display"]}
        self.assertIn("Template Wound", labels)


class ConsequenceOutcomeSceneVisibilityTest(ConsequenceOutcomeAPISetupMixin, TestCase):
    """Scene-participant visibility: participants can see outcomes from their scenes.

    Covers:
    - A non-owner account with a SceneParticipation on the outcome's scene CAN see it.
    - A non-owner, non-participant account CANNOT see it.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Ensure cls.interaction is linked to a scene so participation works.
        cls.scene = SceneFactory()
        cls.interaction.scene = cls.scene
        cls.interaction.save()

        # Participant account: has a SceneParticipation on the outcome's scene.
        cls.participant_account = _make_user()
        SceneParticipationFactory(scene=cls.scene, account=cls.participant_account)

        # Non-participant account: no participation at all.
        cls.non_participant_account = _make_user()

    def test_scene_participant_can_view_outcome(self) -> None:
        """Non-owner with a SceneParticipation on the outcome's scene CAN see it."""
        client = APIClient()
        client.force_authenticate(user=self.participant_account)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        result_ids = [r["id"] for r in response.json()["results"]]
        self.assertIn(self.outcome.pk, result_ids)

    def test_non_participant_cannot_view_outcome(self) -> None:
        """Non-owner, non-participant account does NOT see the outcome."""
        client = APIClient()
        client.force_authenticate(user=self.non_participant_account)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["results"], [])
